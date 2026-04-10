"""
Core sentiment analysis functions using LLM.
"""
import asyncio
import re
import json
import pandas as pd
from sentence_transformers import SentenceTransformer
from openai import OpenAI, AsyncOpenAI

from .config import (
    DEFAULT_ASPECTS,
    SENTENCE_TRANSFORMER_MODEL,
    OPENAI_MODEL,
    OPENAI_MAX_TOKENS,
    get_openai_api_key
)

# Initialize models (lazy loading)
_sentence_model = None
_openai_client = None
_async_openai_client = None


def _get_sentence_model():
    """Lazy load sentence transformer model."""
    global _sentence_model
    if _sentence_model is None:
        _sentence_model = SentenceTransformer(SENTENCE_TRANSFORMER_MODEL)
    return _sentence_model


def _get_openai_client():
    """Lazy load OpenAI client."""
    global _openai_client
    if _openai_client is None:
        api_key = get_openai_api_key()
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def llm_aspect_sentiment(review: str, aspects: list = None, max_tokens: int = None, domain: str = "product"):
    """
    Analyze aspect-based sentiment using OpenAI LLM.

    Args:
        review: Review text to analyze
        aspects: List of aspects to analyze (defaults to DEFAULT_ASPECTS)
        max_tokens: Maximum tokens for response (defaults to OPENAI_MAX_TOKENS)
        domain: The domain/type of review (e.g. "movie", "restaurant", "software")

    Returns:
        List of dictionaries with aspect and sentiment
    """
    if aspects is None:
        aspects = DEFAULT_ASPECTS
    if max_tokens is None:
        max_tokens = OPENAI_MAX_TOKENS

    client = _get_openai_client()

    prompt = f"""
You are analyzing a {domain} review for aspect-based sentiment.
Aspects: {", ".join(aspects)}.
For each aspect, return one of: "positive","negative","not_mentioned".
- "positive": the review expresses a favorable opinion about this aspect
- "negative": the review expresses an unfavorable opinion about this aspect
- "not_mentioned": the review does not discuss this aspect at all
Return STRICT JSON ONLY as an array of objects:
[{{"aspect":"acting","sentiment":"positive"}}, ...]
Review:
{review}
""".strip()

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=max_tokens,
    )

    txt = resp.choices[0].message.content.strip()

    # Try direct JSON parse first
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        # If the model accidentally wrapped in ```json fences, strip them & keep just the array
        try:
            txt_clean = re.sub(r"^```json\s*|\s*```$", "", txt, flags=re.I).strip()
            start, end = txt_clean.find("["), txt_clean.rfind("]")
            if start != -1 and end != -1:
                txt_clean = txt_clean[start: end + 1]
            return json.loads(txt_clean)
        except (json.JSONDecodeError, ValueError) as e:
            # If all parsing attempts fail, raise a more informative error
            raise ValueError(
                f"Failed to parse OpenAI response as JSON. Response was: {txt[:200]}..."
            ) from e


def _get_async_openai_client():
    """Lazy load async OpenAI client."""
    global _async_openai_client
    if _async_openai_client is None:
        api_key = get_openai_api_key()
        _async_openai_client = AsyncOpenAI(api_key=api_key)
    return _async_openai_client


async def async_llm_aspect_sentiment(
    review: str,
    aspects: list = None,
    max_tokens: int = None,
    domain: str = "product",
) -> list[dict]:
    """
    Async version of llm_aspect_sentiment using AsyncOpenAI.
    """
    if aspects is None:
        aspects = DEFAULT_ASPECTS
    if max_tokens is None:
        max_tokens = OPENAI_MAX_TOKENS

    client = _get_async_openai_client()

    prompt = f"""
You are analyzing a {domain} review for aspect-based sentiment.
Aspects: {", ".join(aspects)}.
For each aspect, return one of: "positive","negative","not_mentioned".
- "positive": the review expresses a favorable opinion about this aspect
- "negative": the review expresses an unfavorable opinion about this aspect
- "not_mentioned": the review does not discuss this aspect at all
Return STRICT JSON ONLY as an array of objects:
[{{"aspect":"acting","sentiment":"positive"}}, ...]
Review:
{review}
""".strip()

    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=max_tokens,
    )

    txt = resp.choices[0].message.content.strip()

    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        try:
            txt_clean = re.sub(r"^```json\s*|\s*```$", "", txt, flags=re.I).strip()
            start, end = txt_clean.find("["), txt_clean.rfind("]")
            if start != -1 and end != -1:
                txt_clean = txt_clean[start: end + 1]
            return json.loads(txt_clean)
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(
                f"Failed to parse OpenAI response as JSON. Response was: {txt[:200]}..."
            ) from e


async def async_analyze_batch(
    reviews: list[str],
    aspects: list[str] = None,
    domain: str = "movie",
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

    async def _analyze_one(idx: int, review: str):
        nonlocal completed
        async with semaphore:
            try:
                result = await async_llm_aspect_sentiment(
                    review, aspects, domain=domain
                )
            except Exception as e:
                # On failure, return not_mentioned for all aspects
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
    return results


def analyze(review: str, aspects: list = None, method: str = "LLM (OpenAI)", domain: str = "product"):
    """
    Analyze review sentiment for given aspects using specified method.

    Args:
        review: Review text to analyze
        aspects: List of aspects to analyze (defaults to DEFAULT_ASPECTS)
        method: Analysis method (currently only "LLM (OpenAI)" is supported)
        domain: The domain/type of review (e.g. "movie", "restaurant", "software")

    Returns:
        pandas DataFrame with aspect and sentiment columns
    """
    try:
        if not review:
            return pd.DataFrame([{"aspect": "", "sentiment": "(no review)"}])

        if not aspects:
            aspects = DEFAULT_ASPECTS

        data = llm_aspect_sentiment(review, aspects, domain=domain)

        rows = [
            {
                "aspect": d.get("aspect", ""),
                "sentiment": d.get("sentiment", ""),
            }
            for d in data
        ]
        return pd.DataFrame(rows)

    except Exception as e:
        # Show error context directly in output
        return pd.DataFrame(
            [{"aspect": "(error)", "sentiment": f"{type(e).__name__}: {e}"}]
        )

