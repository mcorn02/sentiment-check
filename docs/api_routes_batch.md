# `api/routes/batch.py` — Technical Documentation

---

## 1. Module Overview

**Purpose:** `api/routes/batch.py` implements the asynchronous batch analysis subsystem of the API. It exposes two HTTP endpoints that together form a submit-and-poll workflow:

1. **`POST /analyze/batch`** — Accepts a CSV file upload containing review text, validates and queues an analysis job, and immediately returns a job identifier to the caller.
2. **`GET /jobs/{job_id}`** — Allows callers to poll the status of a previously submitted job, retrieving progress information, per-review predictions, and a final report once processing is complete.

**Responsibilities:**
- Parsing and validating uploaded CSV files via a shared utility (`api/csv_utils`).
- Detecting — or accepting a caller-supplied hint for — the column within the CSV that contains review text.
- Resolving domain configuration from either a saved database record or inline form parameters, with a defined fallback chain.
- Creating and persisting job records before handing off work to a background task.
- Running sentiment analysis over all reviews asynchronously, checkpointing progress every 10 reviews, and storing results or error state upon completion.
- Serving job status, predictions, and a generated report to polling clients.

**Position in the system:** This module is one of the API route modules mounted on the central FastAPI application. It acts as a thin orchestration layer that bridges the HTTP surface with:
- The persistence layer (`api/db`) for job lifecycle management.
- The analysis engine (`app/sentiment_analyzer`) for per-review sentiment inference.
- The report builder (`api/report`) for generating aggregate summaries.
- Shared CSV utilities (`api/csv_utils`) for file I/O and column detection.

It is the primary entry point for bulk and offline review processing, as distinct from single-review synchronous analysis provided by other route modules.

---

## 2. Key Components

### Constants

#### `_SNIPPET_LEN`

```python
_SNIPPET_LEN: int = 120
```

Controls the maximum character length of the `review_snippet` stored alongside each prediction record. Reviews are truncated to this length when persisting results, keeping the database payload compact while still providing human-readable context for each prediction.

---

### Private Helpers

#### `_now`

```python
def _now() -> str:
```

**What it does:** Returns the current UTC timestamp as an ISO 8601 string.

**Parameters:** None.

**Returns:** `str` — e.g., `"2024-06-01T12:34:56.789012+00:00"`

**Side effects:** None.

**Used by:** `_run_batch_job` (to stamp `completed_at` and error timestamps) and `submit_batch` (to stamp `created_at` when inserting a new job).

---

#### `_detect_review_column`

```python
def _detect_review_column(df, hint):
    """Backward-compat wrapper — delegates to shared utility."""
    return detect_review_column(df, hint)
```

**What it does:** A thin backward-compatibility shim. Delegates entirely to `api.csv_utils.detect_review_column`. This function retains the original internal call site name to minimize diff noise while the actual detection logic now lives in the shared utility module.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `df` | `pd.DataFrame` | The parsed CSV data frame. |
| `hint` | `str \| None` | Optional caller-supplied column name to prefer. If provided and present in the DataFrame, it is returned immediately. |

**Returns:** `str` — The name of the column identified as containing review text.

**Raises:** `ValueError` — if no suitable column can be identified (propagated from `detect_review_column`).

**Side effects:** None.

**Detection strategy (implemented in `api.csv_utils.detect_review_column`):**
1. If `hint` is provided and exists as a column name, return it immediately.
2. Check for columns matching common candidate names (`"review"`, `"text"`, `"comment"`, `"body"`, `"content"`, `"description"`, `"feedback"`), first exact then case-insensitive.
3. Fall back to the first column with `dtype == object`.
4. Raise `ValueError` with the list of available columns if nothing is found.

---

#### `_run_batch_job`

```python
def _run_batch_job(
    job_id: str,
    reviews: list[str],
    domain_label: str,
    aspects: list[str],
    method: str,
) -> None:
```

**What it does:** The core background worker function. Iterates over every review string, invokes the sentiment analyzer for each, accumulates structured prediction records, checkpoints progress to the database every 10 reviews, and upon full completion builds a summary report and marks the job as complete. If any unhandled exception occurs at any point during processing, the job is marked as failed with the exception message stored for retrieval.

**Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | `str` | UUID string identifying the job record in the database. |
| `reviews` | `list[str]` | All review strings extracted from the uploaded CSV, in original order. |
| `domain_label` | `str` | Human-readable domain name (e.g., `"product"`, `"hotel"`), used by the analyzer and report builder. |
| `aspects` | `list[str]` | Aspect labels to analyze against each review (e.g., `["quality", "price", "delivery"]`). |
| `method` | `str` | Analysis method string (e.g., `"llm"`, `"ml"`), passed directly to `analyze`. |

**Returns:** `None`

**Side effects:**
- Calls `analyze(review, aspects, method, domain=domain_label)` for every review — may invoke external LLM APIs or local ML inference, and is the dominant source of latency.
- Calls `update_job_progress(job_id, i + 1)` every 10 reviews — writes a progress checkpoint to the database.
- Calls `build_report(predictions, domain_label, aspects, include_llm_summary=True)` once, after all reviews are processed — may invoke LLM APIs for summary generation.
- Calls `complete_job(job_id, predictions, report, _now())` on success — writes the full results and final state to the database atomically.
- Calls `fail_job(job_id, str(exc), _now())` on any exception — writes error state to the database.

**Prediction record structure (accumulated per review):**
```python
{
    "review_index": int,       # 0-based position of the review in the original list
    "review_snippet": str,     # First _SNIPPET_LEN (120) characters of the review text
    "results": [
        {
            "aspect": str,     # Aspect label
            "sentiment": str,  # Sentiment classification for that aspect
        },
        # ... one entry per valid aspect result
    ]
}
```

> **Filtering:** Aspect result rows where `aspect` is `""` (empty string) or `"(error)"` are excluded before the prediction record is stored. These sentinel values indicate analysis failures or empty outputs from the underlying analyzer.

**Progress checkpointing:** `update_job_progress` is called after processing reviews at 0-based indices 9, 19, 29, … (i.e., whenever `(i + 1) % 10 == 0`). The final partial batch — when the total review count is not a multiple of 10 — is not checkpointed mid-stream. The definitive final state is written atomically by `complete_job` or `fail_job`.

**Error handling:** A single broad `except Exception` wraps the entire processing loop and report build. Any exception at any stage — including analyzer errors, database write failures, or report generation failures — causes the entire job to be marked as failed. There is no partial-completion state: if the exception is raised after some reviews have been processed, those intermediate results are not persisted.

---

### Router

```python
router = APIRouter(tags=["batch"])
```

A FastAPI `APIRouter` instance. All endpoints defined in this module are grouped under the `"batch"` OpenAPI tag, which controls their grouping in auto-generated API documentation (e.g., Swagger UI). This router is expected to be mounted on the top-level FastAPI application via `app.include_router(router)` or an equivalent mechanism.

---

### Endpoints

#### `POST /analyze/batch`

```python
@router.post("/analyze/batch", response_model=JobSubmitResponse, status_code=202)
async def submit_batch(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="CSV file containing reviews"),
    domain_id: str | None = Form(None, description="Saved domain config ID"),
    domain: str = Form("product", description="Domain label if not using a saved config"),
    aspects: str | None = Form(None, description="Comma-separated aspects to override domain config"),
    method: AnalysisMethod = Form(AnalysisMethod.llm),
    review_column: str | None = Form(None, description="CSV column name containing review text"),
) -> JobSubmitResponse:
```

**What it does:** Accepts a multipart form submission containing a CSV file and analysis configuration parameters. Validates the file, resolves the effective domain label and aspect list according to the precedence rules below, creates a persisted job record, and enqueues the background processing task. Returns immediately with HTTP `202 Accepted` — the response is sent before any analysis begins.

**Form Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file` | `UploadFile` | ✅ Yes | — | CSV file containing review data. Must be parseable and non-empty. |
| `domain_id` | `str \| None` | ❌ No | `None` | ID of a saved domain configuration in the database. When supplied, overrides `domain` for the label and provides aspects if `aspects` is not explicitly set. |
| `domain` | `str` | ❌ No | `"product"` | Domain label to use when `domain_id` is not provided. Ignored if `domain_id` resolves successfully. |
| `aspects` | `str \| None` | ❌ No | `None` | Comma-separated aspect list (e.g., `"quality,price,delivery"`). Overrides domain config aspects when explicitly provided. |
| `method` | `AnalysisMethod` | ❌ No | `AnalysisMethod.llm` | Analysis method enum value. |
| `review_column` | `str \| None` | ❌ No | `None` | Explicit CSV column name to use for review text. If omitted, auto-detection is attempted. |

**Domain and aspect resolution logic (evaluated in order):**

```
1. Initialize:
     domain_label     = <domain form param>   (e.g., "product")
     resolved_aspects = None

2. If aspects form param is provided:
     resolved_aspects = [a.strip() for a in aspects.split(",")]

3. If domain_id form param is provided:
     a. Fetch domain config from DB → HTTP 404 if not found
     b. domain_label    = config["name"]
     c. if resolved_aspects is None:
            resolved_aspects = config["aspects"]

4. If resolved_aspects is still None:
     resolved_aspects = DEFAULT_ASPECTS        (from app.config)
```

**Returns:** `JobSubmitResponse` with HTTP status `202`

```python
JobSubmitResponse(
    job_id="<uuid4-string>",
    status=JobStatus.queued,
    message="Job queued. {N} reviews will be analyzed. Poll GET /jobs/{job_id} for results.",
)
```

**Error responses:**
| HTTP Status | Trigger Condition |
|-------------|-------------------|
| `400 Bad Request` | The uploaded file cannot be parsed as a CSV. |
| `400 Bad Request` | The parsed CSV DataFrame is empty (zero rows). |
| `400 Bad Request` | No review text column can be detected and none was explicitly specified. |
| `400 Bad Request` | The detected or specified review column contains no non-null, non-empty rows. |
| `404 Not Found` | `domain_id` was provided but no matching domain record exists in the database. |

**Side effects:**
- Reads the entire uploaded file content into memory via `await file.read()`.
- Calls `parse_csv_bytes(contents)` to decode and parse the CSV.
- Calls `_detect_review_column(df, review_column)` to identify the text column.
- Calls `get_domain(domain_id)` if `domain_id` is provided.
- Calls `insert_job(job_id, domain_label, method.value, resolved_aspects, len(reviews), _now())` synchronously — the job record exists in the database before the response is sent.
- Enqueues `_run_batch_job(...)` as a FastAPI `BackgroundTask` — execution begins after the response has been delivered to the caller.

---

#### `GET /jobs/{job_id}`

```python
@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
```

**What it does:** Retrieves the current state of a previously submitted batch analysis job. Returns metadata about the job, optional progress information while it is running, and — once processing is complete — the full per-review prediction list and the generated aggregate report.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | `str` | UUID string of the job to query, as returned by `POST /analyze/batch`. |

**Returns:** `JobStatusResponse`

```python
JobStatusResponse(
    job_id=str,                                 # The queried job ID
    status=JobStatus,                           # "queued" | "running" | "complete" | "failed"
    progress=str | None,                        # e.g. "30/150 reviews"; only while queued/running
    error=str | None,                           # Exception message if status == "failed"
    predictions=list[ReviewPrediction] | None,  # Full results; populated on completion
    report=dict | None,                         # Aggregate report; populated on completion
    created_at=str,                             # ISO 8601 UTC creation timestamp
    completed_at=str | None,                    # ISO 8601 UTC completion timestamp
)
```

**Field-level behavior details:**

- **`progress`:** Populated only when `job["status"]` is `"running"` or `"queued"` AND `job["total"]` is truthy (non-zero, non-None). Format: `"{completed}/{total} reviews"`. Will reflect the last checkpoint written by `update_job_progress`, which lags behind the actual processed count by up to 9 reviews.
- **`predictions`:** Each stored prediction dictionary is deserialized into a `ReviewPrediction` model instance, with nested `results` entries converted to `AspectResult` objects.
- **`report`:** Returned as-is from the database record (a dict/JSON object). Only present after `complete_job` has been called.
- **`error`:** Only present (non-None) when `status == "failed"`. Contains the stringified exception from `_run_batch_job`.

**Error responses:**
| HTTP Status | Trigger Condition |
|-------------|-------------------|
| `404 Not Found` | No job record exists with the given `job_id`. |

**Side effects:** Read-only. Calls `get_job(job_id)` and performs no writes.

---

## 3. What Changed

This revision performs a **pure refactoring** of CSV-related logic. No changes were made to the public HTTP API, its request or response shapes, status codes, or observable behavior from the perspective of an API consumer.

---

### 3.1 Removed Imports

```diff
- import io
- import pandas as pd
- from fastapi.responses import JSONResponse
+ from api.csv_utils import detect_review_column, parse_csv_bytes
```

- **`io` and `pandas`:** Previously imported directly to support inline CSV parsing (`pd.read_csv(io.BytesIO(contents), ...)`). These are no longer referenced in the route module; their usage is fully encapsulated within `api/csv_utils`.
- **`JSONResponse`:** Was imported but never used in the version immediately prior to this change. Its removal is dead-code cleanup with no functional impact.
- **`detect_review_column` and `parse_csv_bytes`:** Newly imported from the shared utility module, replacing the previously inline implementations.

**Why it matters:** Removing direct `pandas`
