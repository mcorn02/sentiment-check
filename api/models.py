"""
Pydantic request/response models for the API.
"""
from __future__ import annotations
from pydantic import BaseModel, Field


# ── Domain config ─────────────────────────────────────────────────────────────

class DomainCreate(BaseModel):
    name: str = Field(..., description="Human-readable domain name, e.g. 'restaurant'")
    aspects: list[str] = Field(..., description="Aspects to analyze for this domain")
    description: str | None = Field(None, description="Optional context shown to the LLM")


class DomainResponse(DomainCreate):
    id: str
    is_preset: bool


# ── Report Chat ──────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    report_id: str = Field(..., description="Report ID returned after generation")
    question: str = Field(..., description="User question about the report")
