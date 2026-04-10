"""
Competitive research agent — analyzes the competitive landscape for
sentiment analysis tools and platforms.
"""
import json

from .config import OPENAI_MODEL, OPENAI_MAX_TOKENS
from .sentiment_analyzer import _get_async_openai_client


COMPETITORS = [
    "Brandwatch",
    "MonkeyLearn",
    "Repustate",
    "Qualtrics XM",
    "Medallia",
    "Lexalytics / InMoment",
    "Clarabridge",
]


async def async_research_competitors(focus: str | None = None) -> dict:
    """
    Generate a structured competitive analysis report.

    Args:
        focus: Optional focus area (e.g. "pricing", "features", "target market")

    Returns:
        dict with keys: competitors (list), gaps (list), opportunities (list)
    """
    client = _get_async_openai_client()

    focus_line = f"\nFocus especially on: {focus}" if focus else ""

    prompt = f"""You are a market research analyst specializing in sentiment analysis and customer experience platforms.

Analyze the following competitors in the sentiment analysis / review analytics space:
{chr(10).join(f"- {c}" for c in COMPETITORS)}
{focus_line}

For each competitor, provide:
1. name: company name
2. pricing: pricing model (free tier, per-seat, enterprise-only, etc.)
3. key_features: list of 3-5 standout features
4. strengths: 2-3 key strengths
5. weaknesses: 2-3 known weaknesses or limitations
6. target_market: who they primarily serve

Then identify:
- gaps: 3-5 market gaps that a new entrant could exploit
- opportunities: 3-5 specific opportunities for differentiation

Respond with JSON only:
{{
  "competitors": [
    {{
      "name": "...",
      "pricing": "...",
      "key_features": ["...", "..."],
      "strengths": ["...", "..."],
      "weaknesses": ["...", "..."],
      "target_market": "..."
    }}
  ],
  "gaps": ["...", "..."],
  "opportunities": ["...", "..."]
}}"""

    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=2000,
    )

    raw = resp.choices[0].message.content.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start:end + 1])
        return {"competitors": [], "gaps": [], "opportunities": [], "error": "Failed to parse response"}
