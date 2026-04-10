"""
SSE streaming endpoints for the report pipeline.

POST /report/imdb — IMDB URL scraping flow
POST /report/csv  — CSV upload flow
POST /report/chat — Q&A over a generated report
"""
import asyncio
import json
import re
import uuid

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from api.csv_utils import detect_review_column, parse_csv_bytes
from api.models import IMDBReportRequest, ChatRequest
from app.config import DEFAULT_ASPECTS, MOVIE_ASPECTS, OPENAI_MODEL, OPENAI_MAX_TOKENS
from app.scraper_service import extract_movie_id, scrape_imdb_reviews
from app.report_generator import (
    async_generate_report,
    build_corpus,
    retrieve_for_aspect,
)
from app.sentiment_analyzer import _get_async_openai_client

router = APIRouter(prefix="/report", tags=["report"])

# In-memory cache for generated reports (report_id -> data)
_report_cache: dict[str, dict] = {}

IMDB_URL_RE = re.compile(r"imdb\.com/title/tt\d+", re.I)


def _sse_event(event: str, data: dict) -> str:
    """Format a single SSE event."""
    payload = json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/imdb")
async def imdb_report(request: IMDBReportRequest):
    """
    Stream a movie report via SSE.

    Stages: scraping → analyzing → generating → done
    """
    if not IMDB_URL_RE.search(request.imdb_url):
        raise HTTPException(status_code=400, detail="Please enter a valid IMDB movie URL (imdb.com/title/tt...).")

    try:
        movie_id = extract_movie_id(request.imdb_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    aspects = request.aspects or MOVIE_ASPECTS

    async def event_stream():
        # Stage 1: Scraping
        yield _sse_event("stage", {
            "stage": "scraping",
            "message": f"Scraping reviews from IMDB for {movie_id}...",
        })

        try:
            reviews_data = await asyncio.to_thread(scrape_imdb_reviews, movie_id, 75)
        except Exception as e:
            yield _sse_event("error", {"message": str(e)})
            yield _sse_event("done", {"status": "error"})
            return

        if not reviews_data:
            yield _sse_event("error", {
                "message": f"No reviews found for '{movie_id}' on IMDB.",
            })
            yield _sse_event("done", {"status": "error"})
            return

        review_texts = [r["review_text"] for r in reviews_data if r.get("review_text")]
        movie_title = reviews_data[0].get("movie_title", movie_id) if reviews_data else movie_id

        yield _sse_event("stage", {
            "stage": "scraping",
            "message": f"Scraped {len(review_texts)} reviews for '{movie_title}'",
            "progress": len(review_texts),
            "total": len(review_texts),
            "movie_title": movie_title,
        })

        if len(review_texts) < 10:
            yield _sse_event("warning", {
                "message": f"Only {len(review_texts)} reviews found — results may be less reliable.",
            })

        # Stage 2 & 3: Analysis + Report generation (via async pipeline)
        async def on_stage(stage, data=None):
            if stage == "analyzing":
                event_queue.put_nowait(("stage", {
                    "stage": "analyzing",
                    "message": f"Analyzing sentiment... ({data.get('progress', 0)}/{data.get('total', 0)})",
                    **data,
                }))
            elif stage == "generating":
                event_queue.put_nowait(("stage", {
                    "stage": "generating",
                    "message": data.get("message", "Generating report..."),
                }))
            elif stage == "aspect_complete":
                event_queue.put_nowait(("aspect_complete", data))

        event_queue = asyncio.Queue()

        async def run_report():
            try:
                report = await async_generate_report(
                    review_texts, aspects, on_stage=on_stage, domain="movie"
                )
                event_queue.put_nowait(("_result", report))
            except Exception as e:
                event_queue.put_nowait(("error", {"message": str(e)}))
            finally:
                event_queue.put_nowait(("_done", None))

        task = asyncio.create_task(run_report())

        report_result = None
        while True:
            event_type, event_data = await event_queue.get()
            if event_type == "_done":
                break
            elif event_type == "_result":
                report_result = event_data
                continue
            yield _sse_event(event_type, event_data)

        await task

        if report_result is None:
            yield _sse_event("done", {"status": "error"})
            return

        # Cache corpus + report for chat queries
        report_id = str(uuid.uuid4())
        corpus = await asyncio.to_thread(build_corpus, review_texts)
        _report_cache[report_id] = {
            "corpus": corpus,
            "report": report_result,
            "title": movie_title,
            "movie_title": movie_title,
            "reviews": review_texts,
        }

        # Send chart data
        distributions = []
        for ar in report_result["aspects"]:
            distributions.append({
                "aspect": ar["name"],
                "positive": ar["distribution"]["positive"]["count"],
                "negative": ar["distribution"]["negative"]["count"],
                "not_mentioned": ar["distribution"]["not_mentioned"]["count"],
                "positive_pct": ar["distribution"]["positive"]["pct"],
                "negative_pct": ar["distribution"]["negative"]["pct"],
                "not_mentioned_pct": ar["distribution"]["not_mentioned"]["pct"],
            })

        yield _sse_event("charts", {"distributions": distributions})

        yield _sse_event("report", {
            "report_id": report_id,
            "overall_summary": report_result["overall_summary"],
            "title": movie_title,
            "movie_title": movie_title,
            "n_reviews": report_result["n_reviews"],
            "aspects": report_result["aspects"],
        })

        yield _sse_event("done", {"status": "complete"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/csv")
async def csv_report(
    file: UploadFile = File(..., description="CSV file containing reviews"),
    domain_id: str | None = Form(None, description="Saved domain config ID"),
    domain: str = Form("product", description="Domain label"),
    aspects: str | None = Form(None, description="Comma-separated aspects"),
    review_column: str | None = Form(None, description="CSV column containing review text"),
):
    """
    Stream a report from a CSV upload via SSE.

    Stages: parsing → analyzing → generating → done
    """
    from api.db import get_domain

    # Parse CSV
    contents = await file.read()
    try:
        df = parse_csv_bytes(contents)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty.")

    try:
        col = detect_review_column(df, review_column)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    review_texts = df[col].dropna().astype(str).tolist()
    if not review_texts:
        raise HTTPException(status_code=400, detail="No review text found in the detected column.")

    # Resolve domain + aspects
    domain_label = domain
    resolved_aspects = [a.strip() for a in aspects.split(",")] if aspects else None

    if domain_id:
        domain_cfg = get_domain(domain_id)
        if not domain_cfg:
            raise HTTPException(status_code=404, detail=f"Domain '{domain_id}' not found")
        domain_label = domain_cfg["name"]
        if resolved_aspects is None:
            resolved_aspects = domain_cfg["aspects"]

    if not resolved_aspects:
        resolved_aspects = DEFAULT_ASPECTS

    title = file.filename or "Uploaded Reviews"

    async def event_stream():
        # Stage 1: Parsing complete
        yield _sse_event("stage", {
            "stage": "parsing",
            "message": f"Parsed {len(review_texts)} reviews from '{title}'",
            "progress": len(review_texts),
            "total": len(review_texts),
            "title": title,
        })

        if len(review_texts) < 5:
            yield _sse_event("warning", {
                "message": f"Only {len(review_texts)} reviews found — results may be less reliable.",
            })

        # Stage 2 & 3: Analysis + Report generation
        async def on_stage(stage, data=None):
            if stage == "analyzing":
                event_queue.put_nowait(("stage", {
                    "stage": "analyzing",
                    "message": f"Analyzing sentiment... ({data.get('progress', 0)}/{data.get('total', 0)})",
                    **data,
                }))
            elif stage == "generating":
                event_queue.put_nowait(("stage", {
                    "stage": "generating",
                    "message": data.get("message", "Generating report..."),
                }))
            elif stage == "aspect_complete":
                event_queue.put_nowait(("aspect_complete", data))

        event_queue = asyncio.Queue()

        async def run_report():
            try:
                report = await async_generate_report(
                    review_texts, resolved_aspects, on_stage=on_stage, domain=domain_label
                )
                event_queue.put_nowait(("_result", report))
            except Exception as e:
                event_queue.put_nowait(("error", {"message": str(e)}))
            finally:
                event_queue.put_nowait(("_done", None))

        task = asyncio.create_task(run_report())

        report_result = None
        while True:
            event_type, event_data = await event_queue.get()
            if event_type == "_done":
                break
            elif event_type == "_result":
                report_result = event_data
                continue
            yield _sse_event(event_type, event_data)

        await task

        if report_result is None:
            yield _sse_event("done", {"status": "error"})
            return

        # Cache corpus + report for chat queries
        report_id = str(uuid.uuid4())
        corpus = await asyncio.to_thread(build_corpus, review_texts)
        _report_cache[report_id] = {
            "corpus": corpus,
            "report": report_result,
            "title": title,
            "reviews": review_texts,
        }

        # Send chart data
        distributions = []
        for ar in report_result["aspects"]:
            distributions.append({
                "aspect": ar["name"],
                "positive": ar["distribution"]["positive"]["count"],
                "negative": ar["distribution"]["negative"]["count"],
                "not_mentioned": ar["distribution"]["not_mentioned"]["count"],
                "positive_pct": ar["distribution"]["positive"]["pct"],
                "negative_pct": ar["distribution"]["negative"]["pct"],
                "not_mentioned_pct": ar["distribution"]["not_mentioned"]["pct"],
            })

        yield _sse_event("charts", {"distributions": distributions})

        yield _sse_event("report", {
            "report_id": report_id,
            "overall_summary": report_result["overall_summary"],
            "title": title,
            "n_reviews": report_result["n_reviews"],
            "aspects": report_result["aspects"],
        })

        yield _sse_event("done", {"status": "complete"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat")
async def report_chat(request: ChatRequest):
    """
    Answer a question about a previously generated report using RAG
    over the original review corpus.
    """
    cached = _report_cache.get(request.report_id)
    if not cached:
        raise HTTPException(status_code=404, detail="Report not found. Please generate a report first.")

    corpus = cached["corpus"]
    report = cached["report"]
    title = cached.get("title") or cached.get("movie_title", "this product")

    # Retrieve sentences most relevant to the user's question
    retrieved = await asyncio.to_thread(
        retrieve_for_aspect, request.question, corpus, 15, 40
    )

    quotes_block = "\n".join(
        f'- (review #{r["review_idx"] + 1}, relevance {r["score"]:.2f}) "{r["sentence"]}"'
        for r in retrieved
    )

    # Build aspect summary context
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

    client = _get_async_openai_client()
    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=OPENAI_MAX_TOKENS,
    )

    return {"answer": resp.choices[0].message.content.strip()}
