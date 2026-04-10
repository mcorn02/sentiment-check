# `api/main.py` — Technical Documentation

---

## 1. Module Overview

`api/main.py` is the **application entrypoint** for the **Sentiment Check API**, a FastAPI-based web service providing AI-powered movie review sentiment analysis with aspect-level breakdowns and interactive chat capabilities.

This module is responsible for:

- **Constructing and configuring the `FastAPI` application instance** that is served by an ASGI server (e.g., `uvicorn`).
- **Managing application lifespan** — specifically, initializing the database before the app begins serving requests.
- **Registering CORS middleware** to allow cross-origin requests from known React development server origins.
- **Mounting all API routers** under a unified `/api` prefix, creating a clean separation between API routes and other content.
- **Serving the compiled frontend SPA** (Single-Page Application) in production environments, including a catch-all fallback route for client-side routing.
- **Exposing a health-check endpoint** for uptime monitoring and load-balancer probes.

Within the broader system architecture, this file sits at the **top of the Python package hierarchy** and is the sole module referenced by the ASGI server. It composes together database initialization (`api.db`), route handlers (`api.routes.*`), and static file serving into a single deployable unit.

**How to run:**

```bash
uvicorn api.main:app --reload
```

---

## 2. Key Components

### Constants

---

#### `FRONTEND_DIST`

```python
FRONTEND_DIST: Path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
```

**What it does:** Resolves the absolute filesystem path to the compiled frontend distribution directory. The path is computed relative to this file's location, navigating two levels up (from `api/`) to the project root, then into `frontend/dist/`.

**Side effects / dependencies:**
- Evaluated at **module import time**.
- The value of this constant gates whether static file serving is configured — if the directory does not exist (e.g., in development without a frontend build), the SPA serving block is skipped entirely.
- Assumes a monorepo layout: `<project_root>/frontend/dist/`.

---

### Lifespan Context Manager

---

#### `lifespan`

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    init_db()
    yield
```

**What it does:** Implements the FastAPI [lifespan protocol](https://fastapi.tiangolo.com/advanced/events/). Code before `yield` runs on **startup**; code after `yield` (none here) would run on **shutdown**.

| Parameter | Type | Description |
|-----------|------|-------------|
| `app` | `FastAPI` | The FastAPI application instance (injected by the framework; not used directly in the body). |

**Returns:** An async context manager (used internally by FastAPI; not called directly by user code).

**Side effects:**
- Calls `init_db()` synchronously during application startup, which is expected to create database tables or perform schema migrations.
- Any exception raised in `init_db()` will prevent the application from starting.

---

### Application Instance

---

#### `app`

```python
app = FastAPI(
    title="Sentiment Check API",
    description="AI-powered movie review sentiment analysis with aspect-level breakdowns and interactive chat.",
    version="0.2.0",
    lifespan=lifespan,
)
```

**What it does:** The central `FastAPI` application object. This is the ASGI-callable that `uvicorn` (or any other ASGI server) references directly as `api.main:app`.

**Configuration:**

| Field | Value |
|-------|-------|
| `title` | `"Sentiment Check API"` — appears in auto-generated OpenAPI/Swagger docs |
| `description` | Human-readable summary of the API's purpose; surfaced in `/docs` and `/openapi.json` |
| `version` | `"0.2.0"` — surfaced in the OpenAPI schema |
| `lifespan` | Bound to the `lifespan` async context manager above |

**Registered middleware (applied in order of registration):**

- **`CORSMiddleware`** — see [CORS Middleware Configuration](#cors-middleware-configuration) below.

**Mounted routers (all under `/api` prefix):**

| Router | Prefix | Source Module |
|--------|--------|---------------|
| `analyze_router` | `/api` | `api.routes.analyze` |
| `batch_router` | `/api` | `api.routes.batch` |
| `domains_router` | `/api` | `api.routes.domains` |
| `report_router` | `/api` | `api.routes.report` |
| `research_router` | `/api` | `api.routes.research` |

---

### Middleware

---

#### CORS Middleware Configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**What it does:** Configures Cross-Origin Resource Sharing to allow the React development server to call the API without browser security blocks.

| Parameter | Value | Notes |
|-----------|-------|-------|
| `allow_origins` | Four localhost variants | Covers Vite's default port (`5173`) and CRA's default port (`3000`) on both `localhost` and `127.0.0.1` |
| `allow_credentials` | `True` | Permits cookies and `Authorization` headers in cross-origin requests |
| `allow_methods` | `["*"]` | All HTTP methods permitted |
| `allow_headers` | `["*"]` | All request headers permitted |

**Behavioral note:** In production, when the frontend is served by the same origin as the API (via the SPA static serving block), CORS restrictions do not apply and this middleware is effectively a no-op for frontend traffic.

---

### Endpoints

---

#### `health`

```python
@app.get("/api/health", tags=["meta"])
def health() -> dict:
```

**What it does:** Returns a minimal JSON payload confirming the application is running. Useful for container health checks, load balancer probes, and uptime monitoring.

**Parameters:** None.

**Returns:**

```json
{ "status": "ok" }
```

**Tags:** `meta` (groups this endpoint separately in the OpenAPI UI).

**Notes:** This is a synchronous (`def`, not `async def`) endpoint, which FastAPI runs in a thread pool. It has no database interaction and should respond near-instantly.

---

#### `serve_spa`

```python
@app.get("/{full_path:path}")
async def serve_spa(request: Request, full_path: str) -> FileResponse:
    """SPA fallback: serve index.html for any non-API, non-static route."""
```

> **Conditional registration:** This endpoint is **only registered if `FRONTEND_DIST` is a valid directory** at import time. It will not exist in a pure API/development environment without a frontend build present.

**What it does:** Acts as a catch-all route to support client-side routing in the React SPA. Attempts to serve an exact file match from the `dist/` directory first; falls back to `index.html` for all other paths, allowing React Router (or equivalent) to handle routing client-side.

| Parameter | Type | Description |
|-----------|------|-------------|
| `request` | `Request` | The incoming FastAPI/Starlette request object (available for future use; not actively read in the current implementation). |
| `full_path` | `str` | The path segment captured by `{full_path:path}`, representing everything after the root `/`. |

**Returns:** A `FileResponse`:
- The exact file at `FRONTEND_DIST / full_path` if it exists on disk.
- `FRONTEND_DIST / "index.html"` otherwise.

**Side effects / dependencies:**
- Performs a filesystem existence check (`Path.is_file()`) on each request for non-asset routes.
- Only active when `frontend/dist/` is present (i.e., after `npm run build` or equivalent).
- Because this is a catch-all (`/{full_path:path}`), it is essential that all other routes — including the `/assets` static mount and all `/api` prefixed routes — are registered **before** this handler. FastAPI/Starlette evaluates routes in registration order.

---

### Static File Mount

```python
app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIST / "assets"),
    name="assets",
)
```

> **Conditional registration:** Same condition as `serve_spa` — only active when `FRONTEND_DIST` exists.

**What it does:** Mounts the compiled frontend's `assets/` subdirectory (JavaScript bundles, CSS, fonts, images) at `/assets`, allowing the browser to fetch them with proper caching headers via Starlette's `StaticFiles` handler.

**Notes:**
- This mount is registered **before** the `serve_spa` catch-all route. Starlette/FastAPI evaluates routes in registration order, so `/assets/...` requests are handled by the static file server and never fall through to the SPA handler.
- Static file responses include standard HTTP caching headers managed by `StaticFiles`, enabling browser-level caching of immutable build artifacts.

---

## 3. What Changed

This commit makes a **targeted, additive change** to the application: the `research` router is imported and registered as a new API router under the `/api` prefix.

---

### 3.1 New Import: `research_router`

```diff
+from api.routes.research import router as research_router
```

**What changed:** A new import statement was added to bring in the router defined in `api.routes.research`, aliased as `research_router` for consistency with the naming convention used for other routers in this module.

**Why it matters:** Without this import, the `research` route module would be entirely unreachable by the application, regardless of what endpoints it defines. This is a prerequisite for the router registration below.

---

### 3.2 New Router Registration: `research_router`

```diff
+app.include_router(research_router, prefix="/api")
```

**What changed:** `research_router` is now included in the application's router table under the `/api` prefix, alongside the four previously registered routers (`analyze`, `batch`, `domains`, `report`).

**Why it matters functionally:** This is the change that makes all endpoints defined within `api.routes.research` **publicly reachable** via the running application. Any routes declared in that module (e.g., `GET /api/research/...` or `POST /api/research/...`, depending on what the router defines) are now part of the live API surface and will also appear in the auto-generated OpenAPI schema at `/docs` and `/openapi.json`.

**Behavioral differences from before:**

| Aspect | Before | After |
|--------|--------|-------|
| `api.routes.research` endpoints | Not reachable — module not loaded | Fully reachable under `/api` prefix |
| OpenAPI schema | No research endpoints listed | Research endpoints appear in `/docs` and `/openapi.json` |
| Router count | 4 routers registered | 5 routers registered |
| `api.routes.research` module | Not imported at startup | Imported and initialized at startup |

**Registration order note:** `research_router` is appended after `report_router`, placing it last among the API routers but still before the conditional catch-all `serve_spa` route (if registered). This ordering is correct and ensures the catch-all does not shadow any research API endpoints.

---

### 3.3 No Other Changes

The application title, description, version, CORS middleware configuration, lifespan handler, health endpoint, SPA static file serving logic, and all pre-existing router registrations are **unchanged** in this commit. The diff is entirely contained within the import block and the router registration block.

---

## 4. Dependencies & Integration

### Internal Imports (what this module consumes)

| Import | Source | Purpose |
|--------|--------|---------|
| `init_db` | `api.db` | Initializes the database schema on application startup |
| `analyze_router` | `api.routes.analyze` | Handles single-text sentiment analysis requests |
| `batch_router` | `api.routes.batch` | Handles batch sentiment analysis jobs |
| `domains_router` | `api.routes.domains` | Manages domain definitions/configurations |
| `report_router` | `api.routes.report` | Generates business-level sentiment reports |
| `research_router` | `api.routes.research` | Exposes research-oriented endpoints (newly added) |

### External / Third-Party Imports

| Library | Usage |
|---------|-------|
| `fastapi` | Core web framework — `FastAPI`, `Request` |
| `fastapi.middleware.cors` | `CORSMiddleware` for cross-origin request handling |
| `fastapi.responses` | `FileResponse` for serving static files and the SPA fallback |
| `fastapi.staticfiles` | `StaticFiles` for mounting the frontend assets directory |
| `pathlib` (stdlib) | `Path` for cross-platform filesystem path resolution |
| `contextlib` (stdlib) | `asynccontextmanager` for lifespan event management |
| `os` (stdlib) | Imported but not actively used in current code; likely reserved for future environment variable access |

### What Depends on This Module

| Consumer | How it uses `api/main.py` |
|----------|--------------------------|
| **ASGI server** (`uvicorn`) | References `api.main:app` directly as the ASGI callable. Entry command: `uvicorn api.main:app --reload` |
| **Frontend (React SPA)** | All API calls target routes registered in this module; static file serving is also configured here for production deployments |
| **Health monitoring / load balancers** | Polls `GET /api/health` |
| **OpenAPI clients / SDK generators** | Schema generated from the `app` instance reflects all routers, metadata, and titles defined here — now including the research router's endpoints |

### Filesystem Dependencies

| Path | Required | Purpose |
|------|----------|---------|
| `<project_root>/frontend/dist/` | Optional | Enables SPA static file serving when present |
| `<project_root>/frontend/dist/assets/` | Optional | Mounted at `/assets` for JS/CSS/font bundles |
| `<project_root>/frontend/dist/index.html` | Optional | Served as SPA fallback for all unmatched routes |

---

`FUNCTIONAL_CHANGE: YES`
