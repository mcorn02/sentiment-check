"""
RAG-based report generation over a corpus of reviews.

Builds an embedding index of all review sentences, retrieves the most relevant
snippets per aspect, and uses an LLM to produce a grounded narrative report.
"""
import asyncio
from typing import Callable

import numpy as np
from sentence_transformers import CrossEncoder, util

from .config import (
    CROSS_ENCODER_MODEL,
    DEFAULT_ASPECTS,
    WRITING_EFFORT,
)
from .preprocessing import clean_text, get_sentences
from .sentiment_analyzer import (
    _get_sentence_model,
    async_analyze_batch,
)
from .insights_agent import async_generate_insights
from .llm import complete_text

_reranker_model = None


def _get_reranker_model():
    """Lazy load cross-encoder for re-ranking."""
    global _reranker_model
    if _reranker_model is None:
        _reranker_model = CrossEncoder(CROSS_ENCODER_MODEL)
    return _reranker_model


def build_corpus(reviews: list[str]) -> dict:
    """
    Sentence-tokenize and embed every review into a searchable corpus.

    Returns:
        dict with keys:
        - sentences: list[str]
        - review_indices: list[int]  (which review each sentence came from)
        - embeddings: np.ndarray of shape (n_sentences, dim)
    """
    model = _get_sentence_model()
    all_sentences = []
    review_indices = []

    for idx, review in enumerate(reviews):
        cleaned = clean_text(review)
        sents = get_sentences(cleaned)
        all_sentences.extend(sents)
        review_indices.extend([idx] * len(sents))

    embeddings = model.encode(all_sentences, convert_to_numpy=True)

    return {
        "sentences": all_sentences,
        "review_indices": review_indices,
        "embeddings": embeddings,
    }

def _retrieve_candidates(aspect: str, corpus: dict, k: int = 30) -> list[dict]:
    """
    Retrieve the top-k most relevant sentences for an aspect.

    Returns list of dicts: [{sentence, review_idx, score}, ...]
    """
    model = _get_sentence_model()
    asp_emb = model.encode([aspect], convert_to_numpy=True)
    scores = util.cos_sim(asp_emb, corpus["embeddings"])[0].numpy()
    k = min(k, len(scores))
    top_indices = np.argsort(scores)[::-1][:k]

    results = []
    for i in top_indices:
        results.append({
            "sentence": corpus["sentences"][i],
            "review_idx": corpus["review_indices"][i],
            "score": float(scores[i]),
        })
    return results

def _rerank_candidates(aspect: str, candidates: list[dict], k: int = 10) -> list[dict]:
    """
    Re-rank candidates using a cross-encoder. Returns top-k by relevance.
    """
    if not candidates:
        return []
    model = _get_reranker_model()
    pairs = [(aspect, c["sentence"]) for c in candidates]
    scores = model.predict(pairs)
    if isinstance(scores, np.ndarray):
        scores = scores.tolist()
    indexed = list(zip(candidates, scores))
    indexed.sort(key=lambda x: x[1], reverse=True)
    reranked = []
    for c, score in indexed[:k]:
        c = dict(c)
        c["score"] = float(score)
        reranked.append(c)
    return reranked


def retrieve_for_aspect(aspect: str, corpus: dict, k: int = 10, k_retrieve: int = 30) -> list[dict]:
    """
    Retrieve the top-k most relevant sentences for an aspect.
    First-stage NN retrieves k_retrieve candidates; cross-encoder re-ranks to top k.
    """
    candidates = _retrieve_candidates(aspect, corpus, k=k_retrieve)
    return _rerank_candidates(aspect, candidates, k=k)

def _compute_distribution(aspect_results: list[dict]) -> dict:
    """Count sentiment distribution for a single aspect across all reviews."""
    counts = {"positive": 0, "negative": 0, "not_mentioned": 0}
    for r in aspect_results:
        sentiment = r.get("sentiment", "not_mentioned")
        if sentiment in counts:
            counts[sentiment] += 1
        else:
            counts["not_mentioned"] += 1
    total = sum(counts.values()) or 1
    return {k: {"count": v, "pct": round(v / total * 100, 1)} for k, v in counts.items()}


async def async_generate_aspect_section(
    aspect: str,
    retrieved: list[dict],
    distribution: dict,
) -> str:
    """Write a 2-4 sentence narrative for one aspect, grounded in retrieved quotes."""
    pos_pct = distribution["positive"]["pct"]
    neg_pct = distribution["negative"]["pct"]
    nm_pct = distribution["not_mentioned"]["pct"]

    quotes_block = "\n".join(
        f'- (review #{r["review_idx"] + 1}, relevance {r["score"]:.2f}) "{r["sentence"]}"'
        for r in retrieved
    )

    prompt = f"""You are writing a section of a review analysis report about the aspect "{aspect}".

Sentiment distribution across all reviews:
  Positive: {pos_pct}%  |  Negative: {neg_pct}%  |  Not mentioned: {nm_pct}%

Below are the most relevant sentences from the review corpus for this aspect.
Use them as evidence — quote directly when helpful.

{quotes_block}

Write a concise 2-4 sentence summary of what reviewers praised and criticized
about "{aspect}". Reference specific quotes. Do not invent details beyond the
provided quotes. Start directly with the findings — no preamble."""

    return await complete_text(prompt, effort=WRITING_EFFORT)


async def async_generate_report(
    reviews: list[str],
    aspects: list[str] | None = None,
    emit: Callable[[str, dict], None] | None = None,
    domain: str = "product",
) -> tuple[dict, dict]:
    """
    Async end-to-end report generation with streaming progress.

    Args:
        reviews: List of review texts
        aspects: Aspects to analyze (defaults to DEFAULT_ASPECTS)
        emit: Optional sync callback(event, data) for progress updates.
              Events: "stage", "aspect_complete", "insights".
        domain: Domain label for LLM context (e.g. "restaurant", "software")

    Returns:
        (report, corpus) — report has n_reviews, aspects, overall_summary,
        insights; corpus is the embedding index, returned so callers (chat)
        can reuse it instead of re-embedding every review.
    """
    if not aspects:
        aspects = DEFAULT_ASPECTS

    def _emit(event: str, data: dict) -> None:
        if emit:
            emit(event, data)

    total = len(reviews)

    # Step 1: Concurrent sentiment analysis, with per-review progress.
    # Throttle to ~100 updates max so large uploads don't flood the stream.
    step = max(1, total // 100)

    def _on_analysis_progress(completed: int, total_: int) -> None:
        if completed == total_ or completed % step == 0:
            _emit("stage", {
                "stage": "analyzing",
                "message": f"Analyzing sentiment... ({completed}/{total_})",
                "progress": completed,
                "total": total_,
            })

    _on_analysis_progress(0, total)
    all_results = await async_analyze_batch(
        reviews, aspects, domain=domain, on_progress=_on_analysis_progress,
    )

    # Step 2: Build RAG corpus (CPU-bound — keep it off the event loop)
    _emit("stage", {"stage": "generating", "message": "Building embedding index..."})
    corpus = await asyncio.to_thread(build_corpus, reviews)

    # Step 3: Per-aspect retrieval + narrative (concurrent LLM calls)
    _emit("stage", {"stage": "generating", "message": "Generating aspect narratives..."})

    aspect_data = []
    for aspect in aspects:
        aspect_sentiments = [
            r for review_results in all_results for r in review_results
            if r.get("aspect") == aspect
        ]
        distribution = _compute_distribution(aspect_sentiments)
        retrieved = await asyncio.to_thread(retrieve_for_aspect, aspect, corpus, 10)
        aspect_data.append((aspect, retrieved, distribution))

    narratives = await asyncio.gather(
        *[
            async_generate_aspect_section(aspect, retrieved, distribution)
            for aspect, retrieved, distribution in aspect_data
        ]
    )

    aspect_reports = []
    for (aspect, retrieved, distribution), narrative in zip(aspect_data, narratives):
        report_entry = {
            "name": aspect,
            "distribution": distribution,
            "narrative": narrative,
            "top_quotes": [
                {"sentence": r["sentence"], "review": r["review_idx"] + 1}
                for r in retrieved[:5]
            ],
        }
        aspect_reports.append(report_entry)
        _emit("aspect_complete", report_entry)

    # Step 4: Overall summary
    _emit("stage", {"stage": "generating", "message": "Writing overall summary..."})
    summary_lines = []
    for ar in aspect_reports:
        d = ar["distribution"]
        summary_lines.append(
            f'- {ar["name"]}: {d["positive"]["pct"]}% positive, '
            f'{d["negative"]["pct"]}% negative, '
            f'{d["not_mentioned"]["pct"]}% not mentioned'
        )

    summary_prompt = f"""You are summarizing a review analysis report across {total} reviews.

Aspect-level sentiment breakdown:
{chr(10).join(summary_lines)}

Write a concise 2-3 sentence overall summary highlighting what is working well
and what needs improvement. Be direct and specific."""

    overall_summary = await complete_text(summary_prompt, effort=WRITING_EFFORT)

    # Step 5: Insights
    _emit("stage", {"stage": "generating", "message": "Generating insights..."})
    report_data = {
        "n_reviews": total,
        "aspects": aspect_reports,
        "overall_summary": overall_summary,
    }
    try:
        insights = await async_generate_insights(report_data, domain=domain)
    except Exception:
        insights = []
    report_data["insights"] = insights
    _emit("insights", {"insights": insights})

    return report_data, corpus
