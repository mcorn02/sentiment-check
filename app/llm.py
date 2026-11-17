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
  declines on another model (only for models in `_FALLBACK_MODELS`; Haiku 5.5
  has none); any remaining refusal raises `LLMRefusal`.
- `CLAUDE_MODEL` can be overridden with the CLAUDE_MODEL env var.
"""
from __future__ import annotations

import json

import anthropic

from .config import CLAUDE_MODEL

_FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept server-side refusal fallback. Haiku 5.5 has none.
_FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"}

# Running token totals per model, for cost comparisons in eval scripts.
USAGE: dict[str, dict[str, int]] = {}

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


async def _create(
    prompt: str,
    *,
    effort: str,
    max_tokens: int,
    output_format: dict | None = None,
    model: str | None = None,
):
    model = model or CLAUDE_MODEL
    output_config: dict = {"effort": effort}
    if output_format is not None:
        output_config["format"] = output_format

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        output_config=output_config,
        messages=[{"role": "user", "content": prompt}],
    )
    if model in _FALLBACK_MODELS:
        resp = await get_client().beta.messages.create(
            betas=[_FALLBACK_BETA], fallbacks="default", **kwargs
        )
    else:
        resp = await get_client().messages.create(**kwargs)

    u = USAGE.setdefault(model, {"calls": 0, "input_tokens": 0, "output_tokens": 0})
    u["calls"] += 1
    u["input_tokens"] += resp.usage.input_tokens
    u["output_tokens"] += resp.usage.output_tokens

    if resp.stop_reason == "refusal":
        category = getattr(resp.stop_details, "category", None) if resp.stop_details else None
        raise LLMRefusal(f"Claude declined the request (category: {category}).")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"Claude response hit max_tokens={max_tokens} and was truncated.")

    return "".join(b.text for b in resp.content if b.type == "text").strip()


async def complete_text(
    prompt: str, *, effort: str = "low", max_tokens: int = 4000, model: str | None = None
) -> str:
    return await _create(prompt, effort=effort, max_tokens=max_tokens, model=model)


async def complete_json(
    prompt: str, schema: dict, *, effort: str = "low", max_tokens: int = 4000, model: str | None = None
):
    """Call Claude with structured output. `schema` must be a JSON Schema with additionalProperties: false."""
    text = await _create(
        prompt,
        effort=effort,
        max_tokens=max_tokens,
        output_format={"type": "json_schema", "schema": schema},
        model=model,
    )
    return json.loads(text)
