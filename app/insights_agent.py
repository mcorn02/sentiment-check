"""
Insights agent — generates actionable business insights from a completed report.
"""
import json
from .config import OPENAI_MODEL, OPENAI_MAX_TOKENS
from .sentiment_analyzer import _get_async_openai_client


async def async_generate_insights(report: dict, domain: str = "product") -> list[dict]:
    """
    Analyze a completed report and produce 3-5 structured business insights.

    Returns list of dicts:
        [{"type": "risk"|"strength"|"trend"|"opportunity",
          "severity": "high"|"medium"|"low",
          "title": str,
          "description": str}, ...]
    """
    client = _get_async_openai_client()

    aspect_lines = []
    for ar in report["aspects"]:
        d = ar["distribution"]
        aspect_lines.append(
            f'- {ar["name"]}: {d["positive"]["pct"]}% positive, '
            f'{d["negative"]["pct"]}% negative, '
            f'{d["not_mentioned"]["pct"]}% not mentioned'
        )

    prompt = f"""You are a business analyst reviewing sentiment analysis results for a {domain} domain.

Report summary: {report["overall_summary"]}

Aspect-level breakdown ({report["n_reviews"]} reviews analyzed):
{chr(10).join(aspect_lines)}

Generate 3-5 actionable insights. For each insight, classify it as one of:
- "risk": something that could hurt the business
- "strength": something the business is doing well
- "trend": a notable pattern worth watching
- "opportunity": an area for improvement with high potential

Also assign a severity: "high", "medium", or "low".

Respond with a JSON array only, no other text:
[{{"type": "risk", "severity": "high", "title": "Short title", "description": "1-2 sentence explanation"}}, ...]"""

    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=OPENAI_MAX_TOKENS,
    )

    raw = resp.choices[0].message.content.strip()

    # Parse JSON, handling markdown fences
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start != -1 and end != -1:
            return json.loads(cleaned[start:end + 1])
        return []
