"""
Per-review aspect sentiment labeling with Claude.
"""
import asyncio
import logging

from sentence_transformers import SentenceTransformer

from .config import DEFAULT_ASPECTS, LABEL_EFFORT, SENTENCE_TRANSFORMER_MODEL
from .llm import complete_json

logger = logging.getLogger(__name__)

SENTIMENT_LABELS = ["positive", "negative", "not_mentioned"]

# Lazy-loaded embedding model (shared with report_generator)
_sentence_model = None


def _get_sentence_model():
    """Lazy load sentence transformer model."""
    global _sentence_model
    if _sentence_model is None:
        _sentence_model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
    return _sentence_model


def _label_schema(aspects: list[str]) -> dict:
    """JSON schema with one required enum-valued property per aspect."""
    return {
        "type": "object",
        "properties": {a: {"type": "string", "enum": SENTIMENT_LABELS} for a in aspects},
        "required": list(aspects),
        "additionalProperties": False,
    }


async def async_llm_aspect_sentiment(
    review: str,
    aspects: list = None,
    domain: str = "product",
    model: str | None = None,
    effort: str | None = None,
) -> list[dict]:
    """
    Classify each aspect of one review as positive / negative / not_mentioned.

    Returns [{"aspect": ..., "sentiment": ...}, ...] in the order of `aspects`.
    """
    aspects = list(dict.fromkeys(aspects or DEFAULT_ASPECTS))

    prompt = f"""You are labeling a {domain} review for aspect-based sentiment.

For each aspect, choose one label:
- "positive": the review expresses a favorable opinion about this aspect
- "negative": the review expresses an unfavorable opinion about this aspect
- "not_mentioned": the review does not discuss this aspect

Aspects: {", ".join(aspects)}

<review>
{review}
</review>"""

    labels = await complete_json(
        prompt, _label_schema(aspects), effort=effort or LABEL_EFFORT, max_tokens=2000, model=model
    )
    return [{"aspect": a, "sentiment": labels[a]} for a in aspects]


async def async_analyze_batch(
    reviews: list[str],
    aspects: list[str] = None,
    domain: str = "product",
    max_concurrency: int = 10,
    on_progress: callable = None,
) -> list[list[dict]]:
    """
    Analyze a batch of reviews concurrently using the async OpenAI client.

    Args:
        reviews: List of review texts
        aspects: Aspects to analyze
        domain: Domain label
        max_concurrency: Max concurrent API calls
        on_progress: Optional callback(completed, total) called after each review

    Returns:
        List of result lists, one per review
    """
    if not aspects:
        aspects = DEFAULT_ASPECTS

    semaphore = asyncio.Semaphore(max_concurrency)
    results = [None] * len(reviews)
    completed = 0
    errors: list[Exception] = []

    async def _analyze_one(idx: int, review: str):
        nonlocal completed
        async with semaphore:
            try:
                result = await async_llm_aspect_sentiment(
                    review, aspects, domain=domain
                )
            except Exception as e:
                # On failure, return not_mentioned for all aspects.
                # TODO(labeling rework): count + surface partial failures instead.
                logger.warning("Labeling failed for review %d: %s", idx, e)
                errors.append(e)
                result = [
                    {"aspect": a, "sentiment": "not_mentioned"} for a in aspects
                ]
            results[idx] = result
            completed += 1
            if on_progress:
                on_progress(completed, len(reviews))

    await asyncio.gather(
        *[_analyze_one(i, r) for i, r in enumerate(reviews)]
    )
    # If nothing succeeded (bad key, model unavailable, ...), fail loudly rather
    # than return a report where every aspect is "not_mentioned".
    if reviews and len(errors) == len(reviews):
        raise RuntimeError(f"Sentiment labeling failed for every review: {errors[0]}") from errors[0]
    return results
