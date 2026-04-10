# `api/models.py` — Technical Documentation

## 1. Module Overview

**File path:** `api/models.py`

This module defines all **Pydantic request and response models** (schemas) used throughout the API layer. It serves as the single source of truth for data validation, serialization, and deserialization across all API endpoints.

### Responsibilities

- Declares typed request bodies that FastAPI (or equivalent) deserializes and validates from incoming HTTP JSON payloads.
- Declares typed response models that guarantee consistent, documented JSON output shapes returned to API consumers.
- Defines shared enumerations (`AnalysisMethod`, `JobStatus`) used by both request and response models.
- Provides structured intermediate data types (`AspectResult`, `AspectBreakdown`, `PainPoint`, `Report`, `ReviewPrediction`, etc.) used by the backend pipeline and batch job system.

### Where It Fits in the System

```
HTTP Client
    │
    ▼
API Routes / Endpoints
    │  (use models for request parsing + response shaping)
    ▼
api/models.py  ◄── this file
    │
    ▼
Backend Services / Analyzers / Job Workers
```

All API route handlers depend on this module. It has **no dependencies on other internal modules**, making it a foundational, low-level layer with no circular import risk.

---

## 2. Key Components

### Enumerations

---

#### `AnalysisMethod`

```python
class AnalysisMethod(str, Enum):
    llm = "LLM (OpenAI)"
```

**What it does:** Enumerates the supported sentiment analysis backends. Inherits from `str` so members serialize directly to their string values in JSON output and OpenAPI schemas.

| Member | Value | Description |
|--------|-------|-------------|
| `llm` | `"LLM (OpenAI)"` | Uses the OpenAI API (remote, requires API key) |

> **Note:** Only the `llm` backend is supported. Any request payload containing an unrecognized `method` value will fail Pydantic validation.

---

#### `JobStatus`

```python
class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
```

**What it does:** Represents the full lifecycle state of an asynchronous batch analysis job. Inherits from `str` for transparent JSON serialization.

| Member | Value | Description |
|--------|-------|-------------|
| `queued` | `"queued"` | Job has been accepted but not yet started |
| `running` | `"running"` | Job is actively processing reviews |
| `done` | `"done"` | Job completed successfully; `report` and `predictions` are populated |
| `failed` | `"failed"` | Job encountered a fatal error; `error` field is populated |

---

### Domain Configuration Models

---

#### `DomainCreate`

```python
class DomainCreate(BaseModel):
    name: str = Field(..., description="Human-readable domain name, e.g. 'restaurant'")
    aspects: list[str] = Field(..., description="Aspects to analyze for this domain")
    description: str | None = Field(None, description="Optional context shown to the LLM")
```

**What it does:** Request body model for creating a new analysis domain configuration.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | `str` | ✅ Yes | — | Human-readable label for the domain (e.g., `"restaurant"`, `"hotel"`) |
| `aspects` | `list[str]` | ✅ Yes | — | List of aspects the analysis will evaluate (e.g., `["food", "service", "ambiance"]`) |
| `description` | `str \| None` | ❌ No | `None` | Optional free-text context injected into LLM prompts to improve accuracy |

**Side effects / notes:** When `AnalysisMethod.llm` is used, `description` is passed directly as system-level context to the LLM. It should be written as a concise descriptive string that helps the model understand the domain.

---

#### `DomainResponse`

```python
class DomainResponse(DomainCreate):
    id: str
    is_preset: bool
```

**What it does:** Response model returned when reading or creating a domain. Extends `DomainCreate` with server-assigned identity and classification fields.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Server-generated unique identifier for the domain |
| `is_preset` | `bool` | `True` if this is a built-in preset domain; `False` if user-created |

Inherits all fields from `DomainCreate`: `name`, `aspects`, `description`.

---

### Single-Review Analysis Models

---

#### `AnalyzeRequest`

```python
class AnalyzeRequest(BaseModel):
    review: str
    domain_id: str | None = Field(None, description="Use a saved domain config by ID")
    domain: str = Field("product", description="Domain label if not using a saved config")
    aspects: list[str] | None = Field(None, description="Override aspects from domain config")
    method: AnalysisMethod = AnalysisMethod.llm
```

**What it does:** Request body for the single-review sentiment analysis endpoint. Supports multiple resolution strategies for determining which domain configuration and aspects to use.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `review` | `str` | ✅ Yes | — | The raw review text to analyze |
| `domain_id` | `str \| None` | ❌ No | `None` | ID of a saved `DomainResponse`; if provided, the server loads aspects and description from the stored domain config |
| `domain` | `str` | ❌ No | `"product"` | Fallback domain label used when `domain_id` is absent |
| `aspects` | `list[str] \| None` | ❌ No | `None` | Explicit aspect list; overrides whatever the resolved domain config specifies |
| `method` | `AnalysisMethod` | ❌ No | `AnalysisMethod.llm` | Which analysis backend to invoke |

**Resolution priority (server-side):** `domain_id` (loads saved config) → `aspects` override (overrides config aspects if present) → `domain` fallback label (used when no `domain_id` is given).

---

#### `AspectResult`

```python
class AspectResult(BaseModel):
    aspect: str
    sentiment: str  # positive | negative | not_mentioned
```

**What it does:** Represents the analysis outcome for a single aspect within one review. Used as a building block inside both `AnalyzeResponse` and `ReviewPrediction`.

| Field | Type | Description |
|-------|------|-------------|
| `aspect` | `str` | The aspect name (e.g., `"service"`, `"battery life"`) |
| `sentiment` | `str` | One of `"positive"`, `"negative"`, or `"not_mentioned"` |

**Note:** `sentiment` is typed as plain `str` rather than an `Enum`. This gives the backend flexibility to handle edge-case model outputs while the comment documents the expected contract. Consumers should treat any value outside the three documented strings as an anomaly.

---

#### `AnalyzeResponse`

```python
class AnalyzeResponse(BaseModel):
    domain: str
    aspects: list[str]
    method: str
    results: list[AspectResult]
```

**What it does:** Response body returned by the single-review analysis endpoint. Echoes back the resolved configuration alongside the per-aspect results.

| Field | Type | Description |
|-------|------|-------------|
| `domain` | `str` | The domain label that was used for analysis |
| `aspects` | `list[str]` | The full list of aspects that were evaluated |
| `method` | `str` | Human-readable string of the analysis method used (mirrors `AnalysisMethod` value) |
| `results` | `list[AspectResult]` | One `AspectResult` per aspect in the `aspects` list |

---

### Batch Job Models

---

#### `JobSubmitResponse`

```python
class JobSubmitResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str
```

**What it does:** Immediate acknowledgement response returned when a batch job is accepted for asynchronous processing.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `str` | Unique identifier used to poll for job status |
| `status` | `JobStatus` | Always `JobStatus.queued` at the moment of submission |
| `message` | `str` | Human-readable confirmation string |

---

#### `AspectBreakdown`

```python
class AspectBreakdown(BaseModel):
    aspect: str
    positive_pct: float
    negative_pct: float
    not_mentioned_pct: float
    total_mentioned: int
```

**What it does:** Aggregated sentiment statistics for one aspect computed across all reviews in a completed batch job.

| Field | Type | Description |
|-------|------|-------------|
| `aspect` | `str` | Aspect name |
| `positive_pct` | `float` | Percentage of reviews that mentioned this aspect positively |
| `negative_pct` | `float` | Percentage of reviews that mentioned this aspect negatively |
| `not_mentioned_pct` | `float` | Percentage of reviews that did not mention this aspect |
| `total_mentioned` | `int` | Count of reviews where the aspect was explicitly mentioned (i.e., not `"not_mentioned"`) |

**Note:** Percentages are expected in the range `[0.0, 100.0]`. `positive_pct + negative_pct + not_mentioned_pct` should sum to approximately `100.0`. No Pydantic validator enforces this invariant at the model level.

---

#### `PainPoint`

```python
class PainPoint(BaseModel):
    aspect: str
    negative_count: int
    example_quotes: list[str]
```

**What it does:** Highlights a specific aspect that received significant negative sentiment across the batch, with representative evidence excerpts.

| Field | Type | Description |
|-------|------|-------------|
| `aspect` | `str` | The aspect identified as problematic |
| `negative_count` | `int` | Total number of reviews that rated this aspect negatively |
| `example_quotes` | `list[str]` | Representative review excerpts demonstrating the negative sentiment |

---

#### `Report`

```python
class Report(BaseModel):
    total_reviews: int
    domain: str
    aspects: list[str]
    breakdown: list[AspectBreakdown]
    pain_points: list[PainPoint]  # sorted worst-first
    llm_summary: str | None = None
```

**What it does:** Complete aggregated report produced at the conclusion of a batch job. Embedded inside `JobStatusResponse` when `status` is `done`.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `total_reviews` | `int` | ✅ Yes | — | Total number of reviews processed in the batch |
| `domain` | `str` | ✅ Yes | — | Domain label used for the analysis |
| `aspects` | `list[str]` | ✅ Yes | — | Full list of aspects that were evaluated |
| `breakdown` | `list[AspectBreakdown]` | ✅ Yes | — | Per-aspect statistical breakdown, one entry per aspect |
| `pain_points` | `list[PainPoint]` | ✅ Yes | — | Aspects with high negative sentiment, sorted worst-first by `negative_count` |
| `llm_summary` | `str \| None` | ❌ No | `None` | Optional natural-language narrative summary generated by the LLM after batch completion |

---

#### `ReviewPrediction`

```python
class ReviewPrediction(BaseModel):
    review_index: int
    review_snippet: str  # first 120 chars
    results: list[AspectResult]
```

**What it does:** Per-review prediction record capturing the individual sentiment results for one review in the batch. Collected into the `predictions` list of `JobStatusResponse`.

| Field | Type | Description |
|-------|------|-------------|
| `review_index` | `int` | Zero-based position of this review in the input batch |
| `review_snippet` | `str` | First 120 characters of the review text, used for display and identification purposes |
| `results` | `list[AspectResult]` | Aspect-level sentiment results for this specific review |

---

#### `JobStatusResponse`

```python
class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    progress: str | None = None
    error: str | None = None
    predictions: list[ReviewPrediction] | None = None
    report: Report | None = None
    created_at: str
    completed_at: str | None = None
```

**What it does:** Full job status payload returned by the job polling endpoint. Field availability is conditional on the current `status` value — consumers should check `status` before reading optional fields.

| Field | Type | Available When | Default | Description |
|-------|------|----------------|---------|-------------|
| `job_id` | `str` | Always | — | Unique job identifier |
| `status` | `JobStatus` | Always | — | Current lifecycle state of the job |
| `progress` | `str \| None` | `running` | `None` | Human-readable progress indicator, e.g. `"12/50 reviews"` |
| `error` | `str \| None` | `failed` | `None` | Error message describing why the job failed |
| `predictions` | `list[ReviewPrediction] \| None` | `done` | `None` | Full per-review sentiment results for every review in the batch |
| `report` | `Report \| None` | `done` | `None` | Aggregated batch report with breakdowns, pain points, and optional LLM summary |
| `created_at` | `str` | Always | — | ISO 8601 timestamp of job creation |
| `completed_at` | `str \| None` | `done` / `failed` | `None` | ISO 8601 timestamp of job completion or failure |

---

### Movie Report / SSE Pipeline Models

---

#### `IMDBReportRequest`

```python
class IMDBReportRequest(BaseModel):
    imdb_url: str = Field(..., description="IMDB movie URL")
    aspects: list[str] | None = Field(
        None, description="Aspects to analyze (defaults to movie preset)"
    )
```

**What it does:** Request body for the IMDB review scraping and SSE (Server-Sent Events) streaming analysis pipeline. Triggers a real-time pipeline that fetches reviews from an IMDB movie page and performs aspect-based sentiment analysis, emitting incremental results as server-sent events.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `imdb_url` | `str` | ✅ Yes | — | Full IMDB movie URL (e.g., `https://www.imdb.com/title/tt0111161/`) |
| `aspects` | `list[str] \| None` | ❌ No | `None` | Explicit aspects to evaluate; when `None`, falls back to the built-in movie domain preset |

**Side effects / dependencies:**
- The backend is expected to extract the `tt...` title ID from `imdb_url` for scraping. Malformed or non-IMDB URLs are **not** rejected at the Pydantic model level; validation must occur at the route or service layer.
- When `aspects` is `None`, the server resolves the movie preset domain's aspect list, creating an implicit dependency on the preset domain configuration at the service level.

---

### URL Report Models

---

#### `URLReportRequest`

```python
class URLReportRequest(BaseModel):
    url: str = Field(..., description="Review page URL (IMDB, Google Maps, or Yelp)")
    domain_id: str | None = Field(None, description="Saved domain config ID")
    domain: str = Field("product", description="Domain label if not using a saved config")
    aspects: list[str] | None = Field(
        None, description="Aspects to analyze (defaults to domain config)"
