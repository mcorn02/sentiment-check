# `api/routes/report.py` — Technical Documentation

## 1. Module Overview

### Purpose

`api/routes/report.py` implements four SSE (Server-Sent Events) streaming HTTP endpoints and one JSON endpoint that together form the primary entry point for the review analysis pipeline. Clients submit an IMDB movie URL, a generic review page URL (Google Maps, Yelp, or IMDB), or a CSV file of reviews, receive real-time pipeline progress events via a persistent HTTP stream, and may subsequently ask natural-language questions about the generated report through a conversational Q&A endpoint.

### Responsibilities

- **Input validation**: Validates IMDB URLs against a module-level compiled regex; validates generic URLs by delegating source detection to `detect_source`; validates CSV uploads for parsability, non-emptiness, and the presence of a detectable review column; validates chat requests against a cached `report_id`.
- **Pipeline orchestration**: Coordinates sequential pipeline stages — scraping (IMDB and URL flows) or parsing (CSV flow), sentiment analysis, and report generation — delegating all actual work to service-layer modules.
- **Real-time progress streaming**: Uses an `asyncio.Queue` as an internal message bus to bridge the async report pipeline with the SSE response stream, allowing nested async callbacks to enqueue events for the outer generator to yield without violating Python's generator semantics.
- **SSE event formatting**: Serializes all structured data as correctly delimited SSE frames and assigns semantic event type names so clients can route each message to the appropriate UI handler.
- **Report caching**: Stores generated reports and their associated review corpora in a module-level in-memory dictionary keyed by UUID, enabling subsequent chat queries to operate over the same data without regeneration.
- **Retrieval-Augmented Generation (RAG) for chat**: For the `/chat` endpoint, retrieves the most semantically relevant review sentences for the user's question, constructs a grounded prompt from cached report data, and calls the OpenAI API to produce a cited answer.
- **Error handling and graceful degradation**: Emits structured `error` and `warning` SSE events on all failure conditions rather than terminating the stream silently. A `done` event is always emitted at stream termination regardless of success or failure.

### Position in the System

```
Client (browser / frontend)
        │
        ├─ POST /report/imdb  ─────────────────────────────────────┐
        ├─ POST /report/csv   ─────────────────────────────────────┤
        ├─ POST /report/url   ─────────────────────────────────────┤
        └─ POST /report/chat  ─────────────────────────────────────┤
                                                                    ▼
                                             api/routes/report.py  ← this module
                                                        │
                               ┌────────────────────────┼──────────────────────────┐
                               ▼                        ▼                          ▼
                  app.scraper_service       app.report_generator        app.sentiment_analyzer
                  (blocking I/O,            (async pipeline,            (_get_async_openai_client)
                   run in thread pool)       sentiment + LLM)
                                                        │
                               ┌────────────────────────┤
                               ▼                        ▼
                         api.csv_utils             api.db
                         (parse + detect)          (domain config lookup)
```

This module sits at the API boundary layer. It is a FastAPI `APIRouter` mounted under the `/report` prefix and tagged `"report"` for OpenAPI grouping. It contains no business logic itself; all domain work is delegated to service-layer modules.

---

## 2. Key Components

### 2.1 Module-Level Router

```python
router = APIRouter(prefix="/report", tags=["report"])
```

A FastAPI `APIRouter` instance. All routes defined in this module are prefixed with `/report`. The `"report"` tag groups these endpoints in the generated OpenAPI/Swagger UI documentation. This router must be registered with the main FastAPI application instance via `app.include_router(router)`.

---

### 2.2 Module-Level Constant: `_report_cache`

```python
_report_cache: dict[str, dict] = {}
```

An in-memory dictionary that stores generated report data keyed by a UUID string (`report_id`). Each entry maps a `report_id` to a dictionary containing the following keys:

| Key           | Type        | Present In          | Description                                                                  |
|---------------|-------------|---------------------|------------------------------------------------------------------------------|
| `corpus`      | object      | All flows           | Prebuilt sentence corpus returned by `build_corpus`, used for RAG retrieval  |
| `report`      | `dict`      | All flows           | The full report result from `async_generate_report`                          |
| `title`       | `str`       | All flows           | Human-readable title for the report (filename, movie title, or business name)|
| `movie_title` | `str`       | IMDB flow only      | Movie title; also stored separately for chat prompt labeling                 |
| `reviews`     | `list[str]` | All flows           | Original review text strings                                                 |

> **Limitations**: This cache is process-scoped and non-persistent. All cached reports are lost on server restart. There is no eviction policy; the cache grows unboundedly over time. In a production deployment, this should be replaced with a distributed cache (e.g., Redis) or persistent storage.

---

### 2.3 Module-Level Constant: `IMDB_URL_RE`

```python
IMDB_URL_RE = re.compile(r"imdb\.com/title/tt\d+", re.I)
```

A pre-compiled, case-insensitive regular expression used to validate that submitted URLs conform to the expected IMDB title URL format (e.g., `https://www.imdb.com/title/tt1234567/`). Compiled once at module import time and reused across all requests for efficiency. Used exclusively by `imdb_report`; the more general `url_report` endpoint delegates URL validation to `detect_source`.

---

### 2.4 `_sse_event`

```python
def _sse_event(event: str, data: dict) -> str
```

#### What it does
Formats a single Server-Sent Event frame as a string conforming to the [SSE specification](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events).

#### Parameters

| Parameter | Type   | Description                                                    |
|-----------|--------|----------------------------------------------------------------|
| `event`   | `str`  | The SSE event name (e.g., `"stage"`, `"error"`, `"done"`)     |
| `data`    | `dict` | A JSON-serializable dictionary to be sent as the event payload |

#### Returns
`str` — A correctly formatted SSE string with the following structure:

```
event: <event>
data: <json_payload>

```

The trailing double newline is required by the SSE specification to delimit event boundaries.

#### Side Effects / Dependencies
- Calls `json.dumps` on `data`. Will raise `TypeError` if `data` contains non-JSON-serializable values.
- No I/O or state mutation.
- Private (prefixed with `_`); not intended to be called outside this module.

#### Example Output
```
event: stage
data: {"stage": "scraping", "message": "Scraping reviews from IMDB for tt1234567..."}

```

---

### 2.5 `imdb_report`

```python
@router.post("/imdb")
async def imdb_report(request: IMDBReportRequest) -> StreamingResponse
```

#### What it does
Accepts a POST request containing an IMDB movie URL, validates it, and returns a `StreamingResponse` that streams Server-Sent Events to the client across the full lifecycle of the report pipeline — from scraping through sentiment analysis to report generation.

#### Parameters

| Parameter | Type                | Source              | Description                                                                  |
|-----------|---------------------|---------------------|------------------------------------------------------------------------------|
| `request` | `IMDBReportRequest` | Request body (JSON) | Pydantic model containing `imdb_url: str` and optional `aspects: list[str]` |

#### Returns
`StreamingResponse` with:
- `media_type="text/event-stream"`
- Headers:
  - `Cache-Control: no-cache`
  - `Connection: keep-alive`
  - `X-Accel-Buffering: no` — prevents Nginx reverse proxies from buffering the stream

#### Raises (before streaming begins)

| Condition                                  | HTTP Status | Detail                                                            |
|--------------------------------------------|-------------|-------------------------------------------------------------------|
| URL does not match `imdb\.com/title/tt\d+` | `400`       | `"Please enter a valid IMDB movie URL (imdb.com/title/tt...)"` |
| `extract_movie_id` raises `ValueError`     | `400`       | Exception message propagated verbatim from `extract_movie_id`    |

> **Important**: Once the `StreamingResponse` is returned, subsequent errors are communicated exclusively as SSE `error` events, because HTTP response headers have already been sent to the client.

#### Aspects Resolution

```python
aspects = request.aspects or MOVIE_ASPECTS
```

If the client does not supply an `aspects` list, the module falls back to `MOVIE_ASPECTS` from `app.config`.

#### SSE Events Emitted

The following table describes every SSE event that may be yielded during the stream, in order:

| Event name        | When emitted                                           | Key payload fields                                                            |
|-------------------|--------------------------------------------------------|-------------------------------------------------------------------------------|
| `stage`           | Scraping begins                                        | `stage: "scraping"`, `message`                                                |
| `error`           | Scraping raises an exception or returns no reviews     | `message`                                                                     |
| `done`            | After an `error` event (early exit)                    | `status: "error"`                                                             |
| `stage`           | Scraping succeeds                                      | `stage: "scraping"`, `message`, `progress`, `total`, `movie_title`           |
| `warning`         | Fewer than 10 reviews scraped                          | `message`                                                                     |
| `stage`           | Analysis progress (one or more)                        | `stage: "analyzing"`, `message`, `progress`, `total`, spread `data`          |
| `stage`           | LLM generation begins                                  | `stage: "generating"`, `message`                                              |
| `insights`        | Insight data available during generation               | Contents of `data` from `async_generate_report` callback                      |
| `aspect_complete` | Each aspect finishes analysis                          | Contents of `data` from `async_generate_report` callback                      |
| `error`           | `async_generate_report` raises an exception            | `message`                                                                     |
| `done`            | After `error` from report generation (early exit)      | `status: "error"`                                                             |
| `charts`          | Report generation complete, before final report event  | `distributions` (array of per-aspect sentiment counts and percentages)        |
| `report`          | Final successful report payload                        | `report_id`, `overall_summary`, `title`, `movie_title`, `n_reviews`, `aspects`|
| `done`            | Stream completes successfully                          | `status: "complete"`                                                          |

#### Inner Components

##### `event_stream()` — async generator

The core SSE generator that drives the entire pipeline and yields formatted SSE strings. Passed directly to `StreamingResponse`.

**Stage 1 — Scraping:**

1. Yields a `stage` event (`"stage": "scraping"`) to notify the client that scraping has begun.
2. Calls `scrape_imdb_reviews(movie_id, 75)` in a thread pool via `asyncio.to_thread`, requesting up to 75 reviews.
3. On any exception: yields `error` + `done` events and returns.
4. If no reviews are returned: yields `error` + `done` events with a descriptive message and returns.
5. Extracts `review_texts` (list of non-empty review strings) and `movie_title` from the scraped data.
6. Yields a second `stage` event reporting the count of scraped reviews and the resolved movie title.
7. If fewer than 10 reviews are found, yields a `warning` event.

**Stage 2 & 3 — Analysis + Report Generation:**

Uses an `asyncio.Queue` (`event_queue`) as an internal message bus because nested async callbacks cannot directly `yield` from the outer generator.

1. Defines `on_stage(stage, data)` callback — called by `async_generate_report` during execution — which enqueues SSE events via `event_queue.put_nowait`.
2. Defines `run_report()` coroutine that calls `async_generate_report`, places its result or any exception into the queue, and always signals completion via `("_done", None)` in a `finally` block.
3. Launches `run_report()` as a background task via `asyncio.create_task`.
4. Drains the queue in a `while True` loop, yielding each SSE event to the client, until `"_done"` is dequeued.
5. Awaits the background task to confirm full completion.

**Final Output (on success):**

1. Builds a review corpus via `build_corpus` (in a thread pool) and stores it in `_report_cache` under a new UUID `report_id`.
2. Yields a `charts` event containing per-aspect sentiment distributions (counts and percentages).
3. Yields a `report` event containing `overall_summary`, `movie_title`, `n_reviews`, `aspects`, and `report_id`.
4. Yields a `done` event with `"status": "complete"`.

**Final Output (on failure):**

Yields a `done` event with `"status": "error"` and returns without emitting `charts` or `report` events.

##### `on_stage(stage, data=None)` — async callback (inner)

Defined inside `event_stream`. Acts as the progress callback passed to `async_generate_report`. Routes pipeline stage notifications to the SSE queue.

| `stage` value       | Enqueued Event    | Notes                                                              |
|---------------------|-------------------|--------------------------------------------------------------------|
| `"analyzing"`       | `stage`           | Formats a progress message; spreads all `data` fields into payload |
| `"generating"`      | `stage`           | Signals that LLM report generation has begun                       |
| `"insights"`        | `insights`        | Passes `data` through unchanged for incremental client rendering   |
| `"aspect_complete"` | `aspect_complete` | Passes `data` through unchanged for incremental client rendering   |

Any unrecognized `stage` value is silently ignored.

##### `run_report()` — async coroutine (inner)

Defined inside `event_stream`. Wraps `async_generate_report` and communicates its result or failure back to the streaming loop via the queue.

| Queue message         | Condition                                                    |
|-----------------------|--------------------------------------------------------------|
| `("_result", report)` | Successful completion of `async_generate_report`             |
| `("error", {...})`    | Any unhandled exception during report generation             |
| `("_done", None)`     | Always emitted via `finally`; signals the drain loop to exit |

---

### 2.6 `csv_report`

```python
@router.post("/csv")
async def csv_report(
    file: UploadFile = File(..., description="CSV file containing reviews"),
    domain_id: str | None = Form(None, description="Saved domain config ID"),
    domain: str = Form("product", description="Domain label"),
    aspects: str | None = Form(None, description="Comma-separated aspects"),
    review_column: str | None = Form(None, description="CSV column containing review text"),
) -> StreamingResponse
```

#### What it does
Accepts a multipart form POST containing a CSV file of reviews and optional configuration parameters. Validates the upload, resolves domain configuration and aspects, then streams SSE pipeline events covering parsing, sentiment analysis, report generation, and final output — following the same event-streaming architecture as `imdb_report`.

#### Parameters

| Parameter       | Type          | Source      | Description                                                                      |
|-----------------|---------------|-------------|----------------------------------------------------------------------------------|
| `file`          | `UploadFile`  | Form (file) | The CSV file containing reviews; required                                        |
| `domain_id`     | `str \| None` |
