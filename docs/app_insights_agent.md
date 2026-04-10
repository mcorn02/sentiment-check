# `app/insights_agent.py` — Technical Documentation

---

## 1. Module Overview

**Purpose:**
`insights_agent.py` implements an AI-powered business intelligence layer that post-processes completed sentiment analysis reports. It takes structured report data and uses a large language model (LLM) to synthesize 3–5 actionable, human-readable business insights from the underlying metrics.

**Responsibilities:**
- Formatting aspect-level sentiment distribution data into a readable prompt context
- Constructing a domain-aware prompt for the OpenAI chat completions API
- Invoking the LLM asynchronously to generate categorized, severity-ranked insights
- Parsing and sanitizing the LLM's JSON response, including graceful recovery from markdown-fenced output

**Where it fits in the system:**
This module sits at the **reporting and synthesis layer** of the application pipeline. It is intended to be called *after* sentiment analysis has already been performed and a complete report object has been assembled. It acts as an agent that translates raw statistical data into strategic business language, bridging the gap between machine-generated metrics and human decision-making.

```
[Review Input]
     ↓
[Sentiment Analyzer]
     ↓
[Report Builder / Aggregator]
     ↓
[insights_agent.py]  ← this module
     ↓
[Structured Business Insights (JSON)]
```

---

## 2. Key Components

### Functions

---

#### `async_generate_insights`

```python
async def async_generate_insights(
    report: dict,
    domain: str = "product"
) -> list[dict]
```

**What it does:**
Analyzes a completed sentiment report and produces 3–5 structured business insights by:
1. Extracting aspect-level sentiment distribution data from the report
2. Building a role-prompted LLM query that contextualizes the domain and summarizes the report
3. Sending the prompt to the OpenAI chat completions endpoint asynchronously
4. Parsing and returning the LLM's JSON-formatted insight array

---

**Parameters:**

| Parameter | Type   | Required | Default     | Description |
|-----------|--------|----------|-------------|-------------|
| `report`  | `dict` | Yes      | —           | A completed report dictionary. Must contain the following keys: `"aspects"` (list of aspect result dicts), `"overall_summary"` (str), and `"n_reviews"` (int). Each item in `"aspects"` must contain `"name"` (str) and `"distribution"` (dict with `"positive"`, `"negative"`, and `"not_mentioned"` sub-dicts, each having a `"pct"` key). |
| `domain`  | `str`  | No       | `"product"` | A free-text business domain label (e.g., `"product"`, `"service"`, `"restaurant"`) that contextualizes the prompt sent to the LLM. Influences the tone and framing of the generated insights. |

---

**Returns:**

A `list[dict]`, where each dict represents one business insight with the following schema:

```python
{
    "type":        "risk" | "strength" | "trend" | "opportunity",
    "severity":    "high" | "medium" | "low",
    "title":       str,   # Short descriptive title
    "description": str    # 1–2 sentence explanation
}
```

Insight types are defined as:

| Type          | Meaning |
|---------------|---------|
| `"risk"`        | Something that could hurt the business |
| `"strength"`    | Something the business is doing well |
| `"trend"`       | A notable pattern worth watching |
| `"opportunity"` | An area for improvement with high potential |

Severity levels (`"high"`, `"medium"`, `"low"`) indicate the urgency or importance of the insight.

Returns an **empty list `[]`** if:
- The LLM returns malformed JSON that cannot be parsed even after sanitization.

---

**Side effects:**
- Makes an **asynchronous network call** to the OpenAI API via the async client obtained from `_get_async_openai_client()`.
- Consumes OpenAI API tokens (governed by `OPENAI_MAX_TOKENS`).

---

**Internal behavior — Prompt Construction:**

The function dynamically constructs a structured prompt. The aspect-level breakdown is rendered as a bulleted list. Example:

```
- Battery Life: 82% positive, 10% negative, 8% not mentioned
- Customer Support: 34% positive, 55% negative, 11% not mentioned
```

This is combined with the `overall_summary` and `n_reviews` fields and injected into a role-primed system prompt that instructs the LLM to act as a business analyst.

---

**Internal behavior — JSON Parsing with Fallback:**

The function applies a two-stage parsing strategy to handle LLM output variability:

```python
# Stage 1: Direct parse
try:
    return json.loads(raw)
except json.JSONDecodeError:
    # Stage 2: Strip markdown fences and extract JSON array
    import re
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`")
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start != -1 and end != -1:
        return json.loads(cleaned[start:end + 1])
    return []
```

- **Stage 1:** Attempts a direct `json.loads()` parse of the stripped response.
- **Stage 2 (fallback):** Strips ` ```json ` and ` ``` ` markdown code fences, then locates the outermost `[...]` array boundaries using string search and parses only that slice.
- **Final fallback:** Returns `[]` if no valid JSON array can be extracted.

---

**LLM call configuration:**

| Parameter     | Source              | Notes |
|---------------|---------------------|-------|
| `model`       | `OPENAI_MODEL`      | Imported from `app.config` |
| `max_tokens`  | `OPENAI_MAX_TOKENS` | Imported from `app.config` |
| `temperature` | `0.3` (hardcoded)   | Low temperature for consistent, structured output |
| `messages`    | Single user message | Entire context + instructions in one user turn |

---

## 3. What Changed

This file is **newly introduced** in this commit (`new file mode 100644`). There is no prior version of this module — the diff represents the complete initial implementation.

### What was added

**The entire `insights_agent.py` module**, including:

- **`async_generate_insights` function:** A fully async, LLM-powered insight generation pipeline that did not exist before this commit. This adds a new capability to the application: the ability to translate raw sentiment metrics into categorized, severity-ranked business intelligence without any manual analysis.

- **Dynamic prompt engineering:** The module introduces a structured prompt-building routine that formats aspect-level sentiment distributions into a readable tabular narrative and injects the domain context. This is a new pattern within the project.

- **Robust JSON fallback parsing:** The dual-stage JSON parser (`json.loads` → regex sanitization → bracket extraction) is new infrastructure for handling LLM output non-determinism. This defensive pattern protects the pipeline from breaking when the model wraps its response in markdown code fences.

- **Dependency on `_get_async_openai_client`:** This module reuses the private async OpenAI client factory from `sentiment_analyzer`, establishing a shared client pattern rather than creating a new client instantiation strategy.

### Why the change matters functionally

This module introduces a **qualitatively new user-facing capability**: the application can now go beyond raw sentiment percentages and deliver interpretive, strategic-level outputs. Previously, the system could identify *what* sentiment existed; now it can articulate *what to do about it*. This represents an upgrade from a data reporting tool to a decision-support tool.

The `domain` parameter makes this generalizable across business verticals (products, services, hospitality, etc.) without code changes.

### Behavioral differences from before

Since this is a net-new module, there are no behavioral regressions. However, the following **new behaviors** are introduced to the system:

- Callers of `async_generate_insights` will trigger a **live LLM API call** with real token consumption.
- The function now introduces a **fallback return of `[]`** on total parse failure, which downstream consumers must handle as a possible empty result rather than raising an exception.
- Temperature is fixed at `0.3`, meaning the LLM output will be relatively deterministic and structured, but not fully deterministic across calls.

---

## 4. Dependencies & Integration

### Imports & External Dependencies

| Dependency | Source | Usage |
|---|---|---|
| `json` | Python standard library | Parsing the LLM's JSON response |
| `re` | Python standard library (lazy import) | Stripping markdown fences from LLM output in the fallback path |
| `OPENAI_MODEL` | `app.config` | Specifies which OpenAI model to use for the chat completion request |
| `OPENAI_MAX_TOKENS` | `app.config` | Caps the token length of the LLM response |
| `_get_async_openai_client` | `app.sentiment_analyzer` | Factory function that returns a configured async OpenAI client instance |

> **Note:** `_get_async_openai_client` is a private function (prefixed with `_`) imported from a sibling module. This is a notable coupling — changes to that function's signature or behavior in `sentiment_analyzer.py` will directly affect this module.

---

### What Depends on This Module

As a newly introduced module, `insights_agent.py` is expected to be consumed by:

- **Report orchestration layer / pipeline coordinator** — any module responsible for assembling the final report object and triggering post-processing steps (e.g., a `report_builder.py`, `pipeline.py`, or API route handler) would call `async_generate_insights` after the report is finalized.
- **API endpoint handlers** — if the application exposes a REST or WebSocket API, an endpoint handler would `await` this function and include its output in the response payload.

---

### Expected `report` Object Contract

The function enforces an implicit schema on the `report` argument. The calling code must supply a dict with at minimum:

```python
{
    "overall_summary": str,
    "n_reviews": int,
    "aspects": [
        {
            "name": str,
            "distribution": {
                "positive":      {"pct": float | int},
                "negative":      {"pct": float | int},
                "not_mentioned": {"pct": float | int}
            }
        },
        # ... more aspects
    ]
}
```

Any missing keys will raise a `KeyError` at runtime. There is no input validation guard in the current implementation.

---
