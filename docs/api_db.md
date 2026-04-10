# `api/db.py` — Technical Documentation

---

## 1. Module Overview

**Purpose:** `api/db.py` is the persistence layer for the application. It owns all SQLite database setup, schema definition, and data-access logic for two core entities: **domains** and **jobs**.

**Responsibilities:**

- Defining and resolving the database file path at startup.
- Initializing the SQLite schema (tables) via `init_db()`.
- Seeding a curated set of built-in ("preset") domain configurations on first run.
- Exposing CRUD helpers for `domains` records.
- Exposing lifecycle helpers for `jobs` records (create → progress → complete/fail → query).
- Serializing/deserializing JSON columns transparently so all callers work with native Python types.

**Where it fits:** This module sits at the bottom of the server-side stack. It is imported by API route handlers (e.g., FastAPI/Flask endpoints) and background worker logic that need to read or mutate application state. It has no knowledge of HTTP, business logic, or ML inference — it is purely a data-access layer.

**Storage location:** The database file is stored at `<project_root>/data/api.db`. The directory is created automatically if it does not exist.

---

## 2. Key Components

### Constants

#### `DB_PATH`

```python
DB_PATH: Path = Path(__file__).parent.parent / "data" / "api.db"
```

Absolute path to the SQLite database file, resolved relative to the location of `db.py`. Placing it two levels up from `api/` and into `data/` keeps the database file outside the source tree.

---

#### `PRESETS`

```python
PRESETS: list[dict]
```

A module-level list of dictionaries that defines all built-in domain configurations. Each entry has the following shape:

| Key | Type | Description |
|---|---|---|
| `id` | `str` | Unique slug used as the primary key in the `domains` table |
| `name` | `str` | Human-readable display name |
| `aspects` | `list[str]` | Ordered list of review aspects relevant to this domain |
| `description` | `str` | Short prose description of the domain |
| `is_preset` | `bool` | Always `True` for entries in this list |

**Current presets (7 total):**

| ID | Name | Aspects |
|---|---|---|
| `general` | General | quality, value, service, features, reliability, usability |
| `movie` | Movie | acting_performances, story_plot, pacing, visuals, directing, writing |
| `restaurant` | Restaurant | food_quality, service, ambiance, value_for_money, cleanliness, menu_variety |
| `software` | Software / SaaS | ease_of_use, performance, reliability, customer_support, features, value_for_money |
| `hotel` | Hotel | room_quality, cleanliness, service, location, value_for_money, amenities |
| `ecommerce` | E-Commerce | product_quality, shipping, customer_service, value_for_money, packaging, returns |
| `healthcare` | Healthcare | care_quality, wait_times, staff, communication, facilities, billing |

---

### Connection & Initialization

#### `get_conn()`

```python
def get_conn() -> sqlite3.Connection
```

Opens and returns a new SQLite connection to `DB_PATH`.

**Behavior:**
- Creates the `data/` directory (and any missing parents) if it does not already exist.
- Sets `check_same_thread=False` to allow the connection to be used across threads (required when the connection object is shared in threaded server environments).
- Assigns `sqlite3.Row` as the `row_factory`, so all query results are accessible both by column name and by index.

**Returns:** A configured `sqlite3.Connection` instance.

**Side effects:** May create the `data/` directory on the filesystem.

> **Note:** Each call opens a fresh connection. Callers are responsible for closing it, or should use it as a context manager (`with get_conn() as conn`) to ensure implicit commit/rollback behavior.

---

#### `init_db()`

```python
def init_db() -> None
```

Creates all required tables and seeds preset domain data. Should be called once at application startup.

**Behavior:**
1. Executes a `CREATE TABLE IF NOT EXISTS` script for both `domains` and `jobs` tables, making the call fully idempotent.
2. Calls `_seed_presets()` inside the same connection/transaction to insert any missing preset domains.

**Returns:** `None`

**Side effects:** Writes schema and seed data to the SQLite file. Safe to call multiple times — existing tables and preset rows are never overwritten.

**Schema created:**

```sql
CREATE TABLE IF NOT EXISTS domains (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    aspects     TEXT NOT NULL,   -- JSON array
    description TEXT,
    is_preset   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS jobs (
    id           TEXT PRIMARY KEY,
    status       TEXT NOT NULL DEFAULT 'queued',
    domain       TEXT NOT NULL,
    method       TEXT NOT NULL,
    aspects      TEXT NOT NULL,  -- JSON array
    total        INTEGER,
    completed    INTEGER NOT NULL DEFAULT 0,
    predictions  TEXT,           -- JSON array when done
    report       TEXT,           -- JSON object when done
    error        TEXT,
    created_at   TEXT NOT NULL,
    completed_at TEXT
);
```

---

### Domain Helpers

#### `get_domain()`

```python
def get_domain(domain_id: str) -> dict | None
```

Fetches a single domain record by its primary key.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `domain_id` | `str` | The `id` slug of the domain to retrieve |

**Returns:** A `dict` with all domain fields (`aspects` deserialized to `list[str]`, `is_preset` as `bool`), or `None` if no matching record exists.

**Side effects:** Opens and closes a database connection.

---

#### `list_domains()`

```python
def list_domains() -> list[dict]
```

Returns all domain records, ordered with preset domains first, then alphabetically by name within each group.

**Returns:** A `list` of domain dicts (same shape as `get_domain()`). Returns an empty list if no domains exist.

**Side effects:** Opens and closes a database connection.

---

#### `insert_domain()`

```python
def insert_domain(
    domain_id: str,
    name: str,
    aspects: list[str],
    description: str | None
) -> None
```

Inserts a new user-defined (non-preset) domain into the `domains` table.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `domain_id` | `str` | Unique slug / primary key for the new domain |
| `name` | `str` | Human-readable display name |
| `aspects` | `list[str]` | List of aspect identifiers for this domain |
| `description` | `str \| None` | Optional prose description |

**Returns:** `None`

**Side effects:** Writes one row to the `domains` table. `is_preset` is always stored as `0` (false) for domains inserted via this function. Raises `sqlite3.IntegrityError` if `domain_id` already exists.

---

#### `_seed_presets()` *(private)*

```python
def _seed_presets(conn: sqlite3.Connection) -> None
```

Inserts all entries from `PRESETS` into the `domains` table using `INSERT OR IGNORE`, so existing rows are never overwritten. Called exclusively by `init_db()`.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `conn` | `sqlite3.Connection` | An already-open connection to reuse (avoids opening a second connection inside the same transaction) |

**Returns:** `None`

**Side effects:** May write up to `len(PRESETS)` rows to the `domains` table. Rows with IDs that already exist are silently skipped.

---

#### `_row_to_domain()` *(private)*

```python
def _row_to_domain(row: sqlite3.Row) -> dict
```

Converts a raw `sqlite3.Row` from the `domains` table into a plain Python `dict` with deserialized fields.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `row` | `sqlite3.Row` | A raw row returned from a `domains` query |

**Returns:** A plain `dict` with all domain fields in their Python-native types.

**Transformations applied:**

| Column | Stored as | Returned as |
|---|---|---|
| `aspects` | JSON string | `list[str]` |
| `is_preset` | `int` (0 or 1) | `bool` |

---

### Job Helpers

#### `insert_job()`

```python
def insert_job(
    job_id: str,
    domain: str,
    method: str,
    aspects: list[str],
    total: int,
    created_at: str
) -> None
```

Creates a new job record in the `jobs` table with an initial status of `'queued'`.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `job_id` | `str` | Unique identifier for the job (typically a UUID) |
| `domain` | `str` | Domain ID the job is associated with |
| `method` | `str` | Analysis method/strategy to be applied |
| `aspects` | `list[str]` | Aspects to analyze (serialized to JSON in storage) |
| `total` | `int` | Total number of items to process |
| `created_at` | `str` | ISO 8601 timestamp string of job creation time |

**Returns:** `None`

**Side effects:** Inserts one row into `jobs` with `status='queued'` and `completed=0`. Raises `sqlite3.IntegrityError` if `job_id` already exists.

---

#### `update_job_progress()`

```python
def update_job_progress(job_id: str, completed: int) -> None
```

Updates the progress counter for a running job and transitions its status to `'running'`.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `job_id` | `str` | The job to update |
| `completed` | `int` | Number of items completed so far |

**Returns:** `None`

**Side effects:** Updates `status` → `'running'` and `completed` → the provided value for the matching row. No-ops silently if `job_id` does not exist.

---

#### `complete_job()`

```python
def complete_job(
    job_id: str,
    predictions: list,
    report: dict,
    completed_at: str
) -> None
```

Marks a job as successfully finished, storing its output data.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `job_id` | `str` | The job to finalize |
| `predictions` | `list` | Per-item prediction results (serialized to JSON in storage) |
| `report` | `dict` | Aggregate report object (serialized to JSON in storage) |
| `completed_at` | `str` | ISO 8601 timestamp string of completion time |

**Returns:** `None`

**Side effects:** Updates `status` → `'done'`, populates `predictions`, `report`, and `completed_at`, and sets `completed = total` for the matching row.

---

#### `fail_job()`

```python
def fail_job(job_id: str, error: str, completed_at: str) -> None
```

Marks a job as failed, recording the error message and completion timestamp.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `job_id` | `str` | The job that failed |
| `error` | `str` | Human-readable error message or traceback excerpt |
| `completed_at` | `str` | ISO 8601 timestamp string of when the failure was recorded |

**Returns:** `None`

**Side effects:** Updates `status` → `'failed'`, sets `error` and `completed_at` for the matching row. `predictions` and `report` remain `NULL`.

---

#### `get_job()`

```python
def get_job(job_id: str) -> dict | None
```

Fetches a single job record by its primary key.

**Parameters:**

| Name | Type | Description |
|---|---|---|
| `job_id` | `str` | The job ID to look up |

**Returns:** A `dict` with all job fields, or `None` if not found.

**Deserialization applied to the returned dict:**

| Column | Stored as | Returned as |
|---|---|---|
| `aspects` | JSON string | `list[str]` |
| `predictions` | JSON string or `NULL` | `list` or `None` |
| `report` | JSON string or `NULL` | `dict` or `None` |

All other columns are returned as their native SQLite types (strings and integers).

**Side effects:** Opens and closes a database connection.

---

## 3. What Changed

### Summary of Diff

This commit expanded the `PRESETS` list from 4 entries to 7 by adding three new domain presets: `"general"` (inserted as the first entry, serving as a universal fallback), `"ecommerce"` (for online retail analysis), and `"healthcare"` (for medical provider analysis). No existing presets were modified, and no functions or schema definitions were changed.

---

### Change 1 — New `"general"` preset added as the first entry

```python
{
    "id": "general",
    "name": "General",
    "aspects": ["quality", "value", "service", "features", "reliability", "usability"],
    "description": "General-purpose review analysis for any product or service",
    "is_preset": True,
},
```

**What it does:** Introduces a catch-all domain designed for users who cannot identify a more specific domain that fits their data. Its six aspects — `quality`, `value`, `service`, `features`, `reliability`, `usability` — are intentionally broad and applicable across virtually any product or service category.

**Why it matters functionally:** Before this change, callers passing `domain_id="general"` to `get_domain()` would receive `None`, and any downstream validation that treats an unresolvable domain as an error condition would reject it. After this change, `"general"` is a fully valid, resolvable domain. API endpoints that validate domain IDs before dispatching jobs, as well as any worker logic that loads a domain by ID, will now successfully handle `"general"` without modification.

**Behavioral difference:** `get_domain("general")` previously returned `None`; it now returns a fully populated domain dict. Any UI or API consumer that lists available domains will now see `"General"` as an option.

**Ordering note:** Placing `"general"` first in `PRESETS` has no effect on database insertion order guarantees, but signals its role as the primary default in source code. In `list_domains()`, results are sorted `is_preset DESC, name ASC`, so `"General"` will appear under "G" in the alphabetically ordered preset group in the returned list.

---

### Change 2 — New `"ecommerce"` preset added

```python
{
    "id": "ecommerce",
    "name": "E-Commerce",
    "aspects": ["product_quality", "shipping", "customer_service", "value_for_money", "packaging", "returns"],
    "description": "An online retail product or marketplace",
    "is_preset": True,
},
```

**What it does:** Adds a domain tailored specifically for online retail and marketplace review analysis. Its aspects cover the full customer lifecycle: product evaluation (`product_quality`), fulfillment (`shipping`, `packaging`), post-purchase experience (`returns`), and support/pricing concerns (`customer_service`, `value_for_money`).

**Why it matters functionally:** Aspects like `shipping`, `packaging`, and `returns` are entirely irrelevant to domains such as `restaurant` or `hotel` and would have required a user to manually define a custom domain before this change. With this preset, `domain_id="ecommerce"` now resolves to a valid domain, and its six aspect identifiers become available for job configuration, aspect-level reporting, and any filtering or grouping the application performs on aspect names.

**Behavioral difference:** `get_domain("ecommerce")` previously returned `None`; it now returns a fully populated domain dict.

---

### Change 3 — New `"healthcare"` preset added

```python
{
    "id": "healthcare
