# `app/research_agent.py` — Module Documentation

---

## 1. Module Overview

`research_agent.py` implements an **AI-powered competitive intelligence agent** that analyzes the competitive landscape for sentiment analysis tools and platforms. It is a newly introduced module (added in this commit) that serves as a self-contained research utility within the application.

### Purpose

The module's primary responsibility is to query an OpenAI language model with a structured prompt that instructs it to act as a market research analyst. It targets a fixed, curated list of known competitors in the sentiment analysis / customer experience space and returns a machine-readable competitive analysis report.

### Responsibilities

- Maintaining a canonical list of competitors to analyze (`COMPETITORS`).
- Constructing a detailed, structured prompt for the OpenAI model.
- Calling the OpenAI Chat Completions API asynchronously.
- Parsing and validating the JSON response returned by the model.
- Gracefully recovering from malformed or markdown-wrapped JSON responses.
- Returning a normalized `dict` structure containing competitor profiles, market gaps, and differentiation opportunities.

### System Context

This module sits in the `app` package alongside `sentiment_analyzer.py` (which provides the shared OpenAI client factory) and `config.py` (which provides model configuration). It is designed to be called from higher-level orchestration layers — such as API route handlers, CLI entrypoints, or report-generation pipelines — that need competitive intelligence data on demand.

---

## 2. Key Components

### Constant: `COMPETITORS`

```python
COMPETITORS: list[str] = [
    "Brandwatch",
    "MonkeyLearn",
    "Repustate",
    "Qualtrics XM",
    "Medallia",
    "Lexalytics / InMoment",
    "Clarabridge",
]
```

**Description:**
A module-level list of competitor names that defines the scope of the competitive analysis. These are well-known commercial platforms in the sentiment analysis and customer experience analytics market. The list is embedded directly in the prompt sent to the OpenAI model, meaning any change to this list directly alters the research output.

**Characteristics:**
- Statically defined — not configurable at runtime without modifying the module.
- Contains 7 competitors spanning enterprise CX platforms, NLP-as-a-service tools, and social listening platforms.
- Used exclusively by `async_research_competitors`.

---

### Function: `async_research_competitors`

```python
async def async_research_competitors(focus: str | None = None) -> dict
```

**Description:**
The sole public function in this module. It orchestrates the full flow of generating a structured competitive analysis report by communicating with the OpenAI Chat Completions API. The function is `async` and must be awaited.

#### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `focus` | `str \| None` | No | An optional focus area to direct the model's analysis. Examples: `"pricing"`, `"features"`, `"target market"`. When provided, an additional directive line is appended to the prompt. Defaults to `None` (no special focus). |

#### Return Value

Returns a `dict` with the following structure:

```python
{
    "competitors": [
        {
            "name": str,            # Company name
            "pricing": str,         # Pricing model description
            "key_features": list[str],  # 3–5 standout features
            "strengths": list[str],     # 2–3 key strengths
            "weaknesses": list[str],    # 2–3 known weaknesses/limitations
            "target_market": str    # Primary customer segment
        },
        # ... one entry per competitor in COMPETITORS
    ],
    "gaps": list[str],          # 3–5 exploitable market gaps
    "opportunities": list[str]  # 3–5 differentiation opportunities
}
```

**On parse failure**, returns a degraded fallback dict:

```python
{
    "competitors": [],
    "gaps": [],
    "opportunities": [],
    "error": "Failed to parse response"
}
```

#### Behavior & Internal Flow

1. **Client instantiation:** Calls `_get_async_openai_client()` to obtain a shared async OpenAI client instance.

2. **Prompt construction:** Builds a detailed system-style prompt embedding:
   - A persona instruction (market research analyst).
   - The full `COMPETITORS` list, formatted as a markdown bullet list.
   - An optional focus directive (only included when `focus` is not `None`).
   - Explicit field-by-field instructions for competitor analysis.
   - A JSON-only response requirement with a schema example.

3. **API call:** Invokes `client.chat.completions.create` with:
   - `model`: sourced from `OPENAI_MODEL` config constant.
   - `temperature=0.4`: low-to-moderate temperature for relatively consistent, factual output.
   - `max_tokens=2000`: hard cap on response length (note: `OPENAI_MAX_TOKENS` is imported but **not used** here — see [Dependencies & Integration](#4-dependencies--integration)).

4. **Response parsing (primary path):** Attempts direct `json.loads()` on the stripped response content.

5. **Response parsing (fallback path):** If `json.JSONDecodeError` is raised (e.g., the model wraps output in a markdown code fence), the fallback:
   - Strips markdown code fence delimiters (` ```json ` or ` ``` `) using a regex.
   - Locates the outermost `{` and `}` characters to extract the JSON object.
   - Attempts `json.loads()` on the extracted substring.
   - Returns the error fallback dict if this also fails.

#### Side Effects

- Makes a **network call** to the OpenAI API. Latency and token consumption apply.
- Consumes OpenAI API credits based on prompt + response token count.
- The `re` module is imported **lazily** (inside the `except` block) to avoid importing it on every call.

#### Dependencies

- Requires a valid OpenAI API key to be configured (managed by `_get_async_openai_client()`).
- Must be called within an active async event loop (e.g., via `asyncio.run()` or from within an `async` context).

---

## 3. What Changed

This commit introduces `app/research_agent.py` as a **brand new file**. There is no prior version of this module — the diff is entirely additive.

### What Was Added

#### The entire module (88 lines)

| Element | Details |
|---------|---------|
| Module docstring | Documents purpose as a competitive research agent |
| `COMPETITORS` constant | Defines the 7-item competitor list |
| `async_research_competitors()` | Full async function with prompt engineering, API call, and two-stage JSON parsing |

### Why This Change Matters Functionally

1. **New capability surface:** The application gains an entirely new functional domain — automated competitive intelligence — that did not exist before. Callers can now programmatically obtain structured, AI-generated market analysis without any manual research effort.

2. **Optional focus parameter:** The `focus` parameter makes the function flexible without requiring callers to construct prompts themselves. A single function call can be directed toward pricing analysis, feature comparison, or target market research by simply passing a string.

3. **Resilient JSON parsing:** The two-stage parse strategy (direct attempt → fallback regex extraction) makes the function robust against a known failure mode of LLMs: wrapping JSON output in markdown code fences despite instructions to the contrary. This defensive parsing avoids hard failures in production.

4. **Async-first design:** The function is designed as a coroutine from the outset, aligning with the rest of the application's async architecture (as evidenced by reusing `_get_async_openai_client` from `sentiment_analyzer.py`).

### Behavioral Notes

- The `OPENAI_MAX_TOKENS` import from `config` is present but **unused** — the hardcoded `max_tokens=2000` is used in the API call instead. This may be an oversight or intentional override; it has no runtime impact beyond a minor unused-import warning.
- The `re` module is imported inside the exception handler rather than at the top of the file. This is an unconventional pattern; it functions correctly but may confuse linters or readers expecting all imports at module level.

---

## 4. Dependencies & Integration

### Imports & Upstream Dependencies

| Import | Source | Purpose |
|--------|--------|---------|
| `json` | Python stdlib | Parsing the OpenAI model's JSON response |
| `re` | Python stdlib | Fallback regex cleanup of markdown-wrapped JSON (lazy import) |
| `OPENAI_MODEL` | `app.config` | Specifies which OpenAI model to use for the API call |
| `OPENAI_MAX_TOKENS` | `app.config` | Imported but **not used** in the current implementation |
| `_get_async_openai_client` | `app.sentiment_analyzer` | Factory function that returns a configured async OpenAI client instance |

### What This Module Exposes

| Symbol | Type | Public? |
|--------|------|---------|
| `COMPETITORS` | `list[str]` | Yes — module-level constant |
| `async_research_competitors` | `async function` | Yes — primary public API |

### Downstream Integration Points

This module is designed to be consumed by:

- **API route handlers** that expose a `/research` or `/competitive-analysis` endpoint.
- **CLI entrypoints** that generate and print/save competitive reports.
- **Report generation pipelines** that combine competitive intelligence with sentiment analysis results.
- **Scheduled jobs or background workers** that periodically refresh competitive analysis data.

### Architectural Coupling

```
app/config.py
    └── OPENAI_MODEL, OPENAI_MAX_TOKENS
            └──> app/research_agent.py

app/sentiment_analyzer.py
    └── _get_async_openai_client()
            └──> app/research_agent.py

app/research_agent.py
    └── async_research_competitors()
            └──> [API routes / CLI / pipelines]
```

The module deliberately reuses `_get_async_openai_client` from `sentiment_analyzer.py` rather than instantiating its own client, which promotes client sharing and consistent configuration across the application. However, this creates a coupling to an internal/private function (denoted by the leading underscore), which may be a point of refactoring if the client factory is later promoted to a shared utility module.

---

`FUNCTIONAL_CHANGE: YES`
