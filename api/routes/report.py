"""
SSE streaming endpoints for the report pipeline.

POST /report/upload — upload a file of reviews, stream back a report
POST /report/chat   — Q&A over a previously generated report
"""
import asyncio
import json
import uuid
from collections import OrderedDict

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from api.db import get_domain
from api.models import ChatRequest
from api.upload_parsing import UploadError, parse_upload
from app.config import DEFAULT_ASPECTS, WRITING_EFFORT
from app.report_generator import async_generate_report, retrieve_for_aspect
from app.llm import complete_text

router = APIRouter(prefix="/report", tags=["report"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Reports kept in memory for follow-up chat. Bounded LRU: the oldest report is
# evicted once the cap is hit, so memory doesn't grow without limit.
_REPORT_CACHE_MAX = 20
_report_cache: "OrderedDict[str, dict]" = OrderedDict()


def _cache_report(report_id: str, entry: dict) -> None:
    _report_cache[report_id] = entry
    _report_cache.move_to_end(report_id)
    while len(_report_cache) > _REPORT_CACHE_MAX:
        _report_cache.popitem(last=False)


def _sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _sse_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _stream_report(review_texts: list[str], aspects: list[str], domain: str, title: str):
    """
    Shared SSE pipeline: run the report generator, forward its progress events,
    then emit charts + final report. Used by every input route.
    """
    yield _sse_event("stage", {
        "stage": "parsing",
        "message": f"Loaded {len(review_texts)} reviews from '{title}'",
        "progress": len(review_texts),
        "total": len(review_texts),
        "title": title,
    })

    if len(review_texts) < 5:
        yield _sse_event("warning", {
            "message": f"Only {len(review_texts)} reviews found — results may be less reliable.",
        })

    queue: asyncio.Queue = asyncio.Queue()
    _DONE = object()

    async def run():
        try:
            result = await async_generate_report(
                review_texts, aspects, emit=lambda e, d: queue.put_nowait((e, d)), domain=domain,
            )
            queue.put_nowait(("_result", result))
        except Exception as e:
            queue.put_nowait(("error", {"message": str(e)}))
        finally:
            queue.put_nowait((_DONE, None))

    task = asyncio.create_task(run())
    result = None
    try:
        while True:
            event, data = await queue.get()
            if event is _DONE:
                break
            if event == "_result":
                result = data
                continue
            yield _sse_event(event, data)
    finally:
        # If the client disconnects mid-stream, stop burning API calls.
        if not task.done():
            task.cancel()

    if result is None:
        yield _sse_event("done", {"status": "error"})
        return

    report, corpus = result
    report_id = str(uuid.uuid4())
    _cache_report(report_id, {"corpus": corpus, "report": report, "title": title})

    yield _sse_event("charts", {"distributions": [
        {
            "aspect": ar["name"],
            **{k: ar["distribution"][k]["count"] for k in ("positive", "negative", "not_mentioned")},
            **{f"{k}_pct": ar["distribution"][k]["pct"] for k in ("positive", "negative", "not_mentioned")},
        }
        for ar in report["aspects"]
    ]})

    yield _sse_event("report", {
        "report_id": report_id,
        "overall_summary": report["overall_summary"],
        "title": title,
        "n_reviews": report["n_reviews"],
        "aspects": report["aspects"],
    })
    yield _sse_event("done", {"status": "complete"})


def _resolve_domain(domain_id: str | None, domain: str, aspects: list[str] | None) -> tuple[str, list[str]]:
    """Resolve the domain label + aspect list from a saved config and/or explicit overrides."""
    if domain_id:
        cfg = get_domain(domain_id)
        if not cfg:
            raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
        domain = cfg["name"]
        if aspects is None:
            aspects = cfg["aspects"]
    return domain, aspects or DEFAULT_ASPECTS


@router.post("/upload")
async def upload_report(
    file: UploadFile = File(..., description="Reviews file: csv, tsv, xlsx, json, jsonl, or txt"),
    domain_id: str | None = Form(None, description="Saved domain config ID"),
    domain: str = Form("product", description="Domain label"),
    aspects: str | None = Form(None, description="Comma-separated aspects"),
    review_column: str | None = Form(None, description="Column/key containing review text"),
):
    """
    Stream a report for an uploaded file of reviews via SSE.

    Stages: parsing → analyzing → generating → done
    """
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")

    try:
        review_texts = parse_upload(file.filename or "", contents, (review_column or "").strip() or None)
    except UploadError as e:
        raise HTTPException(status_code=400, detail=str(e))

    parsed_aspects = [a.strip() for a in aspects.split(",") if a.strip()] if aspects else None
    domain_label, resolved_aspects = _resolve_domain(domain_id, domain, parsed_aspects)

    title = file.filename or "Uploaded Reviews"
    return _sse_response(_stream_report(review_texts, resolved_aspects, domain_label, title))


@router.post("/chat")
async def report_chat(request: ChatRequest):
    """
    Answer a question about a previously generated report using RAG
    over the original review corpus.
    """
    cached = _report_cache.get(request.report_id)
    if not cached:
        raise HTTPException(status_code=404, detail="Report not found. Please generate a report first.")
    _report_cache.move_to_end(request.report_id)

    corpus = cached["corpus"]
    report = cached["report"]
    title = cached["title"]

    retrieved = await asyncio.to_thread(
        retrieve_for_aspect, request.question, corpus, 15, 40
    )

    quotes_block = "\n".join(
        f'- (review #{r["review_idx"] + 1}, relevance {r["score"]:.2f}) "{r["sentence"]}"'
        for r in retrieved
    )

    aspect_summaries = "\n".join(
        f'- {a["name"]}: {a["distribution"]["positive"]["pct"]}% positive, '
        f'{a["distribution"]["negative"]["pct"]}% negative — {a["narrative"]}'
        for a in report["aspects"]
    )

    prompt = f"""You are a helpful assistant answering questions about "{title}" based on an analysis of {report["n_reviews"]} reviews.

Here is the report summary:
{report["overall_summary"]}

Aspect-level analysis:
{aspect_summaries}

Below are the most relevant sentences from the review corpus for the user's question.
Use them as evidence — quote directly when helpful.

{quotes_block}

Answer the user's question based on the review data above. Be specific and reference actual reviewer quotes. If the reviews don't contain enough information to answer, say so.

User question: {request.question}"""

    answer = await complete_text(prompt, effort=WRITING_EFFORT)
    return {"answer": answer}
