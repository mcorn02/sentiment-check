"""
Shared Claude client + call helpers. Every LLM call in the app goes through here.

- `complete_text`  — free-form text (narratives, summary, chat answers)
- `complete_json`  — structured output constrained to a JSON schema
                     (per-review labels, insights); returns parsed JSON

Notes for Claude Sonnet 5.5:
- Adaptive thinking is on by default; depth is controlled with `effort`.
  `max_tokens` covers thinking + answer, so don't set it too tight.
- Non-default `temperature` is rejected, so none is sent.
- Server-side fallback (`fallbacks: "default"`) retries certain safety
  declines on another model; any remaining refusal raises `LLMRefusal`.
"""
from __future__ import annotations

import json

import anthropic

from .config import CLAUDE_MODEL

_FALLBACK_BETA = "server-side-fallback-2026-07-01"

_client: anthropic.AsyncAnthropic | None = None


class LLMRefusal(RuntimeError):
    """Claude declined the request (stop_reason == "refusal")."""


def get_client() -> anthropic.AsyncAnthropic:
    """Lazy-load the async client. Reads ANTHROPIC_API_KEY (loaded from .env by config)."""
    global _client
    if _client is None:
        # Extra retries: batch labeling fires many concurrent requests and may hit 429s.
        _client = anthropic.AsyncAnthropic(max_retries=4)
    return _client


async def _create(prompt: str, *, effort: str, max_tokens: int, output_format: dict | None = None):
    output_config: dict = {"effort": effort}
    if output_format is not None:
        output_config["format"] = output_format

    resp = await get_client().beta.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        betas=[_FALLBACK_BETA],
        fallbacks="default",
        output_config=output_config,
        messages=[{"role": "user", "content": prompt}],
    )

    if resp.stop_reason == "refusal":
        category = getattr(resp.stop_details, "category", None) if resp.stop_details else None
        raise LLMRefusal(f"Claude declined the request (category: {category}).")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"Claude response hit max_tokens={max_tokens} and was truncated.")

    return "".join(b.text for b in resp.content if b.type == "text").strip()


async def complete_text(prompt: str, *, effort: str = "low", max_tokens: int = 4000) -> str:
    return await _create(prompt, effort=effort, max_tokens=max_tokens)


async def complete_json(prompt: str, schema: dict, *, effort: str = "low", max_tokens: int = 4000):
    """Call Claude with structured output. `schema` must be a JSON Schema with additionalProperties: false."""
    text = await _create(
        prompt,
        effort=effort,
        max_tokens=max_tokens,
        output_format={"type": "json_schema", "schema": schema},
    )
    return json.loads(text)
