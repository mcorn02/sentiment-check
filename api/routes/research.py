"""
Competitive research endpoint — internal/admin tool.
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.research_agent import async_research_competitors

router = APIRouter(prefix="/research", tags=["research"])


class ResearchRequest(BaseModel):
    focus: str | None = None


@router.post("/competitors")
async def research_competitors(request: ResearchRequest | None = None):
    """Run competitive research analysis and return structured report."""
    focus = request.focus if request else None
    result = await async_research_competitors(focus=focus)
    return result
