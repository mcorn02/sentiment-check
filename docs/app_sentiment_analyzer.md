# `app/sentiment_analyzer.py` — Technical Documentation

---

## 1. Module Overview

`sentiment_analyzer.py` is the **core analytical engine** of the application. It is responsible for performing aspect-based sentiment analysis (ABSA) on free-text reviews using the OpenAI Chat Completions API (GPT models).

Within the broader system architecture, this module sits between the **configuration layer** (`config.py`) and any **user-facing or orchestration layer** (e.g., REST API, CLI, or batch processing script). It exposes both synchronous and asynchronous public interfaces, making it suitable for single-review interactive use as well as high-throughput concurrent batch workloads.

### Primary Responsibilities

| Responsibility | Mechanism |
|---|---|
| Aspect-based sentiment classification | OpenAI LLM via Chat Completions API |
| Lazy model/client initialization | Module-level singletons with guard checks |
| Concurrent batch processing | `asyncio` + `AsyncOpenAI` with semaphore control |
| Unified DataFrame output | `analyze()` entry point |
| Fault tolerance | Per-review error handling with fallback values |

---

## 2. Key Components

### 2.1 Module-Level Singletons

These private globals hold lazily initialized model and client instances. They are `None` at import time and are populated on first use by their respective loader functions.

```python
_sentence_model: SentenceTransformer | None = None
_openai_client: OpenAI | None = None
_async_openai_client: AsyncOpenAI | None = None
```

> **Note:** `_sentence_model` is retained in the module for structural consistency and potential future use, but it is not directly invoked by any currently active public function.

---

### 2.2 Private Loader Functions

These functions implement the **lazy-loading pattern**, ensuring expensive model downloads and API client instantiations only happen when actually needed.

---

#### `_get_sentence_model()`

```python
def _get_sentence_model() -> SentenceTransformer
```

**What it does:** Returns the shared `SentenceTransformer` model instance, initializing it from `SENTENCE_TRANSFORMER_MODEL` on first call. Subsequent calls return the already-initialized singleton without re-loading.

**Side effects:** Populates `_sentence_model`; may trigger a model download on first use.

**Dependencies:** `SENTENCE_TRANSFORMER_MODEL` config constant.

---

#### `_get_openai_client()`

```python
def _get_openai_client() -> OpenAI
```

**What it does:** Returns the shared synchronous `OpenAI` client, retrieving the API key via `get_openai_api_key()` on first call. Subsequent calls return the cached singleton.

**Side effects:** Populates `_openai_client`.

**Dependencies:** `get_openai_api_key()` from `config`.

---

#### `_get_async_openai_client()`

```python
def _get_async_openai_client() -> AsyncOpenAI
```

**What it does:** Returns the shared `AsyncOpenAI` client for use in async coroutines. Created with the same API key retrieval mechanism as the synchronous client. Subsequent calls return the cached singleton.

**Side effects:** Populates `_async_openai_client`.

**Dependencies:** `get_openai_api_key()` from `config`, `AsyncOpenAI` from `openai`.

---

### 2.3 Public Analysis Functions

---

#### `llm_aspect_sentiment()`

```python
def llm_aspect_sentiment(
    review: str,
    aspects: list = None,
    max_tokens: int = None,
    domain: str = "product"
) -> list[dict]
```

**What it does:** Performs aspect-based sentiment analysis by sending the review to the OpenAI Chat Completions API with a structured prompt. The model is instructed to classify each specified aspect and return a strict JSON array mapping each aspect to a sentiment label.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `review` | `str` | — | Raw review text to analyze |
| `aspects` | `list[str]` | `DEFAULT_ASPECTS` | Aspects to classify; falls back to config default when `None` |
| `max_tokens` | `int` | `OPENAI_MAX_TOKENS` | Maximum response tokens; falls back to config default when `None` |
| `domain` | `str` | `"product"` | Domain context injected into the prompt (e.g., `"movie"`, `"restaurant"`, `"software"`) |

**Returns:** `list[dict]` — each dict contains:
- `"aspect"` (`str`): the aspect label
- `"sentiment"` (`str`): one of `"positive"`, `"negative"`, `"not_mentioned"`

**JSON parsing strategy (two-stage):**
1. **Stage 1 — Direct parse:** Attempts `json.loads()` on the raw response string.
2. **Stage 2 — Fence stripping:** If Stage 1 fails, uses a regex (`re.sub`) to strip Markdown code fences (` ```json `), then locates the outermost `[` and `]` boundaries and retries `json.loads()` on the extracted substring.

**Raises:** `ValueError` with a truncated (200-character) preview of the raw response if both parsing stages fail.

**API behaviour:** Called with `temperature=0` for fully deterministic, reproducible output.

**LLM prompt structure:** The prompt instructs the model to act as a domain-specific reviewer, defines the three valid sentiment labels with explicit descriptions, and demands strict JSON output with no surrounding prose.

**Dependencies:** `_get_openai_client()`, `OPENAI_MODEL`, `OPENAI_MAX_TOKENS`, `DEFAULT_ASPECTS`.

---

#### `async_llm_aspect_sentiment()`

```python
async def async_llm_aspect_sentiment(
    review: str,
    aspects: list = None,
    max_tokens: int = None,
    domain: str = "product"
) -> list[dict]
```

**What it does:** The `async`/`await` counterpart of `llm_aspect_sentiment()`. Functionally identical in prompt construction, JSON parsing logic, and return format, but uses `AsyncOpenAI` and `await`-based I/O to avoid blocking the event loop during the API call.

**Parameters:** Identical to `llm_aspect_sentiment()`.

**Returns:** Identical structure to `llm_aspect_sentiment()` — `list[dict]` with `"aspect"` and `"sentiment"` keys.

**Raises:** `ValueError` on JSON parse failure, using the same two-stage strategy as the synchronous version.

**When to use:** Use this function when operating inside an `async` context — most commonly as the per-review worker called by `async_analyze_batch()`, or within an async web framework handler. Do **not** call from synchronous code without wrapping in `asyncio.run()`.

**Dependencies:** `_get_async_openai_client()`, `OPENAI_MODEL`, `OPENAI_MAX_TOKENS`, `DEFAULT_ASPECTS`.

---

#### `async_analyze_batch()`

```python
async def async_analyze_batch(
    reviews: list[str],
    aspects: list[str] = None,
    domain: str = "movie",
    max_concurrency: int = 10,
    on_progress: callable = None
) -> list[list[dict]]
```

**What it does:** Processes a list of reviews **concurrently** by dispatching each to `async_llm_aspect_sentiment()`. Concurrency is bounded via an `asyncio.Semaphore` to prevent overwhelming the OpenAI API with too many simultaneous requests. All tasks are launched together with `asyncio.gather()`, and results are written back into a pre-allocated list by index to preserve ordering.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `reviews` | `list[str]` | — | Collection of raw review texts to process |
| `aspects` | `list[str]` | `DEFAULT_ASPECTS` | Aspects to analyze across all reviews |
| `domain` | `str` | `"movie"` | Domain context for the LLM prompt, applied uniformly to all reviews |
| `max_concurrency` | `int` | `10` | Maximum number of simultaneous in-flight API calls; controls the semaphore count |
| `on_progress` | `callable` | `None` | Optional callback invoked as `on_progress(completed: int, total: int)` after each review finishes; useful for progress bars or logging |

**Returns:** `list[list[dict]]` — a list of result sets in the **same order** as the input `reviews` list. Each inner list matches the return structure of `async_llm_aspect_sentiment()`.

**Error handling:** If `async_llm_aspect_sentiment()` raises any exception for a given review, that review's slot in the results list is silently replaced with a fallback:

```python
[{"aspect": a, "sentiment": "not_mentioned"} for a in aspects]
```

This preserves result index alignment and prevents a single API failure from aborting the entire batch.

**Ordering guarantee:** Results preserve input order regardless of API completion order. The internal `_analyze_one` coroutine writes to a pre-allocated `results` list by index (`results[idx]`), so concurrent completions do not cause ordering issues.

**Concurrency model:**

```
reviews[0] ─┐
reviews[1] ─┤                  ┌── _analyze_one(0) ─ semaphore ─ async API call
reviews[2] ─┼─ asyncio.gather ─┤── _analyze_one(1) ─ semaphore ─ async API call
  ...        │                  └── _analyze_one(N) ─ (waits for semaphore slot)
reviews[N] ─┘
```

**Side effects:** Calls `on_progress(completed, total)` after each review completes if the callback is provided.

**Dependencies:** `asyncio.Semaphore`, `asyncio.gather`, `async_llm_aspect_sentiment`, `DEFAULT_ASPECTS`.

---

#### `analyze()`

```python
def analyze(
    review: str,
    aspects: list = None,
    method: str = "LLM (OpenAI)",
    domain: str = "product"
) -> pd.DataFrame
```

**What it does:** The **primary synchronous entry point** for single-review analysis. Delegates to `llm_aspect_sentiment()`, normalizes the result into a pandas DataFrame, and handles all exceptions gracefully by returning a descriptive error-row DataFrame rather than propagating the exception to the caller.

**Parameters:**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `review` | `str` | — | Raw review text |
| `aspects` | `list[str]` | `DEFAULT_ASPECTS` | Aspects to classify |
| `method` | `str` | `"LLM (OpenAI)"` | Analysis method selector; accepted for API compatibility but currently ignored — see note below |
| `domain` | `str` | `"product"` | Domain context passed through to the LLM prompt |

**Returns:** `pd.DataFrame` with the following columns:

| Column | Type | Description |
|---|---|---|
| `aspect` | `str` | The aspect label |
| `sentiment` | `str` | One of `"positive"`, `"negative"`, `"not_mentioned"` |

**Special return cases:**

| Condition | Returned DataFrame |
|---|---|
| `review` is empty, `None`, or otherwise falsy | Single row: `aspect=""`, `sentiment="(no review)"` |
| Any unhandled exception during analysis | Single row: `aspect="(error)"`, `sentiment="<ExceptionType>: <message>"` |

> **Note on `method` parameter:** The parameter is accepted in the function signature to preserve the public API shape, but it currently has **no branching effect**. All calls route exclusively to `llm_aspect_sentiment()` regardless of the value passed. Callers passing `method="Zero-shot NLI (local)"` or any other value will silently receive LLM results.

**Dependencies:** `llm_aspect_sentiment`, `pandas`, `DEFAULT_ASPECTS`.

---

## 3. What Changed

This update represents a **significant simplification** of the module: the entire Zero-shot NLI (local model) analysis pathway has been removed, leaving OpenAI LLM as the sole supported analysis backend.

### 3.1 Removed: Zero-Shot NLI Infrastructure

The following components were entirely deleted from the module.

#### Removed imports

```python
# Deleted
import torch
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
```

Along with the config constants they depended on:

```python
# Deleted from config imports
DEFAULT_NLI_THRESHOLD,
DEFAULT_ZSC_THRESHOLD,
ZERO_SHOT_MODEL,
```

And the preprocessing utility import:

```python
# Deleted
from .preprocessing import clean_text, get_sentences
```

#### Removed module-level singleton

```python
# Deleted
_zsc_pipeline = None
```

#### Removed private loader function

```python
# Deleted
def _get_zsc_pipeline() -> pipeline
```

This lazily loaded the Hugging Face zero-shot classification pipeline using `ZERO_SHOT_MODEL` on CPU (`device=-1`).

#### Removed embedding utility functions

All three embedding/retrieval helpers that supported the NLI pathway were deleted:

| Function | What it did |
|---|---|
| `embed_sentences(sentences, aspects)` | Encoded sentences and aspects into tensors using `SentenceTransformer` |
| `top_k_sentences_per_aspect(sentences, sent_emb, aspects, asp_emb, k=3)` | Retrieved top-k most semantically similar sentences per aspect via cosine similarity |
| `concat_asp_sentences(top3)` | Joined retrieved sentences into per-aspect text snippets for NLI input |

#### Removed public function: `nli_aspect_sentiment()`

```python
# Deleted
def nli_aspect_sentiment(
    review: str,
    aspects: list = None,
    threshold: float = None
) -> list[dict]
```

This was the primary NLI analysis function. It:
1. Cleaned and sentence-split the review via `clean_text()` / `get_sentences()`
2. For short reviews (≤ 3 sentences), used the full cleaned text per aspect
3. For longer reviews, used the embedding pipeline to find the top-3 most relevant sentences per aspect
4. Passed each aspect snippet to the zero-shot classification pipeline with hypothesis template `"The sentiment towards {aspect} is {}."`
5. Applied a confidence `threshold` to collapse low-confidence predictions to `"not_mentioned"`
6. Returned `list[dict]` with `"aspect"`, `"sentiment"`, **and `"confidence"`** keys

> **Behavioral difference:** `nli_aspect_sentiment()` included a `"confidence"` key (a float score) in each output dict. The LLM pathway does not produce confidence scores. This field no longer exists in **any** output from this module. Downstream consumers that read `result["confidence"]` will receive a `KeyError`.

---

### 3.2 Modified: `analyze()` — Method Dispatch Removed

**Before:**
```python
if method == "LLM (OpenAI)":
    data = llm_aspect_sentiment(review, aspects, domain=domain)
else:  # Zero-shot NLI
    data = nli_aspect_sentiment(review, aspects)
```

**After:**
```python
data = llm_aspect_sentiment(review, aspects, domain=domain)
```

The `method` parameter is still accepted in the function signature (preserving the public API shape), but it no longer branches execution. Any value passed to `method` is silently ignored.

---

### 3.3 Updated: Module Docstring

```python
# Before
"""Core sentiment analysis functions using LLM and Zero-shot NLI methods."""

# After
"""Core sentiment analysis functions using LLM."""
```

---

### 3.4 Why These Changes Matter

| Impact Area | Effect |
|---|---|
| **Dependencies** | Removes `torch` and `transformers` as runtime requirements, significantly reducing the dependency footprint and container/environment size |
| **Startup time** | Eliminates potential model download and initialization overhead for the Hugging Face ZSC pipeline |
| **Public API surface** | `nli_aspect_sentiment()` and all embedding utilities are no longer importable; any caller depending on them will fail with `AttributeError` |
| **Output schema** | The `"confidence"` field produced
