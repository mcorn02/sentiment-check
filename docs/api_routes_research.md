# `api/routes/research.py` — Technical Documentation

---

## 1. Module Overview

**Purpose:**
This module defines the HTTP routing layer for competitive research functionality within the application. It exposes a single REST endpoint that triggers an automated competitive analysis workflow and returns a structured report to the caller.

**Responsibilities:**
- Declare and configure a FastAPI `APIRouter` scoped to the `/research` path prefix.
- Define the request schema for research-related endpoints using a Pydantic model.
- Accept incoming `POST` requests for competitor research, extract optional filtering parameters, delegate execution to the research agent layer, and return the result.

**Position in the System:**
This module sits in the `api/routes/` directory, placing it firmly in the **API routing layer** — one level above the application/business logic layer (`app/`). It acts as a thin adapter between HTTP clients and the `app.research_agent` module, which contains the actual research orchestration logic. The router defined here is expected to be registered with the main FastAPI application instance (e.g., in `main.py` or an equivalent application factory).

> ⚠️ **Internal/Admin Tool:** Per the module docstring, this endpoint is intended for internal or administrative use and should not be exposed as part of a public-facing API without appropriate authentication and authorization guards.

---

## 2. Key Components

### `ResearchRequest`

```python
class ResearchRequest(BaseModel):
    focus: str | None = None
```

**What it does:**
A Pydantic request body model that encapsulates the optional input parameters for a competitive research request.

**Fields:**

| Field   | Type            | Default | Description                                                                 |
|---------|-----------------|---------|-----------------------------------------------------------------------------|
| `focus` | `str` or `None` | `None`  | An optional string that scopes or directs the competitive research analysis. When provided, the research agent uses it to narrow or orient the research output (e.g., a specific product category, market segment, or competitor name). |

**Notes:**
- Inherits from `pydantic.BaseModel`, so it benefits from automatic type validation and coercion on deserialization.
- The entire request body is optional at the endpoint level (see `research_competitors` below), meaning this model will only be instantiated if a body is actually sent.

---

### `router`

```python
router = APIRouter(prefix="/research", tags=["research"])
```

**What it does:**
A FastAPI `APIRouter` instance that namespaces all routes defined in this module under the `/research` URL prefix and groups them under the `"research"` tag in the OpenAPI/Swagger documentation.

**Configuration:**

| Parameter | Value        | Effect                                                                 |
|-----------|--------------|------------------------------------------------------------------------|
| `prefix`  | `"/research"` | All routes defined on this router will be prefixed with `/research`.  |
| `tags`    | `["research"]` | Groups all routes under the `"research"` tag in OpenAPI docs.        |

**Dependencies:**
- Must be registered with the root FastAPI application (via `app.include_router(router)`) to be active.

---

### `research_competitors`

```python
@router.post("/competitors")
async def research_competitors(request: ResearchRequest | None = None) -> Any:
```

**Full resolved path:** `POST /research/competitors`

**What it does:**
Handles POST requests to trigger a competitive research analysis. It extracts the optional `focus` parameter from the request body (if provided), delegates the analysis to `async_research_competitors`, and returns the structured result directly as the HTTP response body.

**Parameters:**

| Parameter | Type                        | Source       | Required | Description                                                                                       |
|-----------|-----------------------------|--------------|----------|---------------------------------------------------------------------------------------------------|
| `request` | `ResearchRequest` or `None` | Request body | No       | Optional JSON request body. If omitted entirely or sent as `null`, `focus` defaults to `None` and the research agent runs without a specific focus scope. |

**Return Value:**
- Returns whatever object `async_research_competitors` resolves to. FastAPI will serialize this to JSON automatically. The exact shape of the response is determined by the return type of `app.research_agent.async_research_competitors`. No explicit response model is declared, so the OpenAPI schema for this response will be untyped (`{}` / `any`).

**Behavior:**
1. If `request` is `None` (no body sent), `focus` is set to `None`.
2. If `request` is provided but `request.focus` is `None` (body sent without `focus` field, or with `"focus": null`), `focus` is also `None`.
3. If `request.focus` is a non-empty string, that value is forwarded to the agent.

**Side Effects:**
- Invokes `async_research_competitors`, which likely performs I/O-bound operations (web scraping, API calls, LLM inference, etc.). The `async` keyword ensures this runs non-blockingly within FastAPI's async event loop.
- No direct database writes, cache mutations, or filesystem interactions are performed within this function itself — such side effects, if any, are owned by the research agent layer.

**Error Handling:**
- No explicit exception handling is present. Any exceptions raised by `async_research_competitors` will propagate up to FastAPI's default exception handler, resulting in a `500 Internal Server Error` response unless a global exception handler is registered elsewhere.

---

## 3. What Changed

This file is **newly introduced** in this commit (the diff shows `new file mode 100644`). There is no prior version to compare against. The following describes what was established:

### What Was Added

| Element                   | Description                                                                                      |
|---------------------------|--------------------------------------------------------------------------------------------------|
| **New module file**       | `api/routes/research.py` created from scratch.                                                   |
| **`ResearchRequest` model** | A new Pydantic schema providing a typed, validated interface for accepting research parameters over HTTP. |
| **`router` instance**     | A new `APIRouter` establishing the `/research` namespace within the API routing hierarchy.        |
| **`POST /research/competitors` endpoint** | A new HTTP endpoint providing external (admin/internal) access to the competitor research agent. |

### Why the Change Matters Functionally

Prior to this commit, the `async_research_competitors` function in `app.research_agent` had no HTTP interface — it could only be invoked programmatically from within the Python application. This change **exposes the competitive research capability as a REST API endpoint**, enabling:

- Administrative tooling and scripts to trigger research runs via HTTP.
- Integration with frontend dashboards, scheduled jobs, or CI/CD pipelines through standard HTTP calls.
- Optional scoping of research via the `focus` parameter, allowing callers to direct the analysis without modifying application code.

### Behavioral Differences from Before

Since this is a net-new file, there is no prior behavior. The system now accepts `POST /research/competitors` requests where it did not before.

---

## 4. Dependencies & Integration

### Imports / Upstream Dependencies

| Import                                          | Source Package  | Role                                                                                                  |
|-------------------------------------------------|-----------------|-------------------------------------------------------------------------------------------------------|
| `APIRouter`                                     | `fastapi`        | Provides the router object for declaring and grouping HTTP routes.                                    |
| `BaseModel`                                     | `pydantic`       | Base class for the `ResearchRequest` schema, enabling data validation and serialization.             |
| `async_research_competitors`                    | `app.research_agent` | The core async function that performs the competitive analysis. This is the primary business logic dependency. |

### Downstream / Integration Points

| Consumer                          | How It Uses This Module                                                                                       |
|-----------------------------------|---------------------------------------------------------------------------------------------------------------|
| **Main FastAPI application**      | Must call `app.include_router(router)` (likely in `main.py` or `api/__init__.py`) to mount the `/research` routes into the running application. Without this, the endpoint is unreachable. |
| **HTTP clients / admin tools**    | Any HTTP client (curl, Postman, internal scripts) targeting `POST /research/competitors` with an optional JSON body `{"focus": "..."}`. |
| **OpenAPI / Swagger UI**          | FastAPI auto-generates documentation for this endpoint, grouped under the `"research"` tag, making it discoverable via `/docs` or `/redoc`. |

### Dependency Graph (Simplified)

```
HTTP Client
    │
    ▼
POST /research/competitors          ← api/routes/research.py
    │
    ▼
async_research_competitors(focus)   ← app/research_agent.py
    │
    ▼
[External APIs / LLMs / Web]
```

---
