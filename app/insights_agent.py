"""
Insights agent — generates actionable business insights from a completed report.
"""
from .config import WRITING_EFFORT
from .llm import complete_json

_INSIGHTS_SCHEMA = {
    "type": "object",
    "properties": {
        "insights": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["risk", "strength", "trend", "opportunity"]},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["type", "severity", "title", "description"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["insights"],
    "additionalProperties": False,
}


async def async_generate_insights(report: dict, domain: str = "product") -> list[dict]:
    """
    Analyze a completed report and produce 3-5 structured business insights.

    Returns list of dicts:
        [{"type": "risk"|"strength"|"trend"|"opportunity",
          "severity": "high"|"medium"|"low",
          "title": str,
          "description": str}, ...]
    """
    aspect_lines = []
    for ar in report["aspects"]:
        d = ar["distribution"]
        aspect_lines.append(
            f'- {ar["name"]}: {d["positive"]["pct"]}% positive, '
            f'{d["negative"]["pct"]}% negative, '
            f'{d["not_mentioned"]["pct"]}% not mentioned'
        )

    prompt = f"""You are a business analyst reviewing sentiment analysis results for a {domain}.

Report summary: {report["overall_summary"]}

Aspect-level breakdown ({report["n_reviews"]} reviews analyzed):
{chr(10).join(aspect_lines)}

Generate 3-5 actionable insights. Classify each as:
- "risk": something that could hurt the business
- "strength": something the business is doing well
- "trend": a notable pattern worth watching
- "opportunity": an area for improvement with high potential

Give each a severity (high, medium, low), a short title, and a 1-2 sentence description."""

    result = await complete_json(prompt, _INSIGHTS_SCHEMA, effort=WRITING_EFFORT)
    return result["insights"]
