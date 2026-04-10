# `api/csv_utils.py` — Technical Documentation

---

## 1. Module Overview

**File path:** `api/csv_utils.py`

**Purpose:**
`csv_utils.py` is a shared utility module providing reusable CSV ingestion and column-detection helpers for the API layer. It centralises logic that would otherwise be duplicated across multiple endpoint handlers.

**Responsibilities:**
- Parsing raw CSV byte payloads (e.g., uploaded files) into structured `pandas` DataFrames, with automatic encoding fallback.
- Detecting which column in a DataFrame contains review/text content, using a priority-ordered heuristic strategy and an optional caller-supplied hint.

**Where it fits in the system:**
This module sits at the boundary between raw user input and the API's business logic. Batch processing endpoints and report generation endpoints are its primary consumers. Rather than each endpoint implementing its own CSV handling, they delegate to these utilities, ensuring consistent parsing behaviour and error messaging across the API surface.

```
[HTTP Upload / Request Body]
         │
         ▼
  parse_csv_bytes()          ← raw bytes → DataFrame
         │
         ▼
  detect_review_column()     ← DataFrame → column name
         │
         ▼
  [Batch / Report Endpoint Logic]
```

---

## 2. Key Components

### `parse_csv_bytes`

```python
def parse_csv_bytes(contents: bytes) -> pd.DataFrame:
```

**What it does:**
Converts a raw CSV byte string (e.g., the body of a file upload) into a `pandas` DataFrame. It attempts UTF-8 decoding first; if any exception is raised during that attempt (including encoding errors or pandas parsing errors), it retries with the `latin-1` encoding. Malformed or unparseable rows are silently skipped in both attempts via `on_bad_lines="skip"`.

**Parameters:**

| Parameter  | Type    | Description                                             |
|------------|---------|---------------------------------------------------------|
| `contents` | `bytes` | Raw byte content of a CSV file (e.g., from an upload). |

**Returns:**

| Type           | Description                                      |
|----------------|--------------------------------------------------|
| `pd.DataFrame` | A DataFrame populated with the CSV's contents.  |

**Side effects & dependencies:**
- Uses `io.BytesIO` to wrap the byte string into a file-like object, avoiding the need to write to disk.
- Relies on `pandas.read_csv` for parsing.
- Silently skips bad lines — callers should be aware that the returned DataFrame may not include every row from the original input if the CSV is malformed.
- If both the UTF-8 and `latin-1` attempts fail (e.g., the content is not a valid CSV at all), the exception from the second attempt propagates to the caller unhandled.

**Encoding fallback rationale:**
UTF-8 is tried first as it is the modern standard. `latin-1` (ISO-8859-1) is a common legacy encoding used in older exports from tools such as Microsoft Excel, particularly for content containing accented or special characters.

---

### `detect_review_column`

```python
def detect_review_column(df: pd.DataFrame, hint: str | None = None) -> str:
```

**What it does:**
Inspects a DataFrame and returns the name of the column most likely to contain free-text review content. Detection follows a four-stage priority strategy:

1. **Hint (exact match):** If `hint` is provided and exactly matches a column name, that column is returned immediately.
2. **Candidate name heuristic:** A priority-ordered list of common column name conventions is checked against the DataFrame's columns, with **case-insensitive** matching. The first match is returned.
3. **First object-dtype column fallback:** If no candidate name matches, the first column whose dtype is `object` (i.e., a string/mixed column in pandas) is returned.
4. **Failure:** If none of the above strategies succeed, a descriptive `ValueError` is raised.

**Candidate name priority order:**

```python
["review", "text", "comment", "body", "content", "description", "feedback"]
```

**Parameters:**

| Parameter | Type             | Description                                                                                                                                                           |
|-----------|------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `df`      | `pd.DataFrame`   | The DataFrame (typically produced by `parse_csv_bytes`) to inspect.                                                                                                   |
| `hint`    | `str` or `None`  | An optional column name supplied by the caller (e.g., from a query parameter or request body). Bypasses heuristic detection if matched exactly. Defaults to `None`. |

**Returns:**

| Type  | Description                                                     |
|-------|-----------------------------------------------------------------|
| `str` | The exact column name (as it appears in `df.columns`) to use.  |

**Raises:**

| Exception    | Condition                                                                                                                                                                        |
|--------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `ValueError` | No column could be identified via hint, candidate matching, or dtype fallback. The error message lists available columns and instructs the caller to pass `review_column` explicitly. |

**Side effects & dependencies:**
- No mutations are made to the input DataFrame.
- Case-insensitive matching in stage 2 uses a list comprehension to lower-case all column names for comparison, then `next()` with a generator to retrieve the original, correctly-cased column name. This ensures the returned name is always a valid key into `df`.
- The `hint` parameter enables the API to expose a `review_column` query/body parameter, giving users an escape hatch when their CSV uses unconventional column names.

**Behavioural edge cases:**

| Scenario | Behaviour |
|---|---|
| `hint` is provided but not found in `df.columns` | The hint is **silently ignored** and heuristic detection continues. No warning or error is raised. |
| Two columns differ only by case (e.g., `"Review"` and `"review"`) | The candidate loop returns whichever appears first in `df.columns` via `next()`. No tie-breaking beyond iteration order. |
| `hint` is an empty string (`""`) | Evaluates as falsy; treated as if no hint was given and heuristic detection proceeds normally. |
| DataFrame has no `object`-dtype columns and no candidate name matches | `ValueError` is raised with a descriptive message listing available column names. |

---

## 3. What Changed

This module is **newly introduced** in this commit (the diff shows `new file mode 100644` with no prior version). The following describes what was established and why it matters.

### What Was Added

The entire `api/csv_utils.py` file was created with two public functions:

- **`parse_csv_bytes`** — encapsulates the CSV parsing pipeline (byte wrapping, encoding fallback, bad-line skipping) that would otherwise need to be written inline in each endpoint.
- **`detect_review_column`** — encapsulates review-column auto-detection logic behind a well-defined interface with a priority-ordered heuristic strategy and an optional caller-supplied override.

### Why the Change Matters Functionally

**Before this commit:** There was no `api/csv_utils.py`. Any batch or report endpoint that needed to ingest CSV data would have had to either:
- Duplicate the parsing and column-detection logic inline, or
- Lack robust encoding fallback and column heuristics entirely.

**After this commit:** A single, consistent implementation is available to all API endpoints. This has several functional consequences:

1. **Consistent encoding handling across all upload endpoints.** All endpoints now transparently handle both UTF-8 and `latin-1` encoded CSVs without any per-endpoint configuration.
2. **User-facing column override (`hint` / `review_column`).** The `hint` parameter in `detect_review_column` establishes a public contract: API consumers can pass a `review_column` parameter to disambiguate their CSV structure. This is a user-visible API capability.
3. **Consistent error messages.** The `ValueError` raised by `detect_review_column` provides a standardised, informative message that endpoints can surface directly to clients.
4. **Bad-line tolerance.** CSVs with isolated malformed rows are silently skipped rather than causing entire upload failures.

### Behavioral Differences From Before

Since this is a net-new file, there are no behavioral regressions. However, any endpoint that **adopts** these utilities will gain the following behaviours where previously it may have had none, or had its own inconsistent implementation:

| Behaviour | Before | After |
|---|---|---|
| Encoding fallback for `latin-1` CSVs | Inconsistent / absent per endpoint | Automatic, universal |
| Heuristic review-column detection | Inconsistent / absent per endpoint | Standardised, priority-ordered |
| User-supplied column name override | Inconsistent / absent per endpoint | Supported via `hint` parameter |
| Malformed row handling | Inconsistent / absent per endpoint | Silently skipped via `on_bad_lines="skip"` |
| Column-detection failure messaging | Inconsistent / absent per endpoint | Standardised `ValueError` with column listing |

---

## 4. Dependencies & Integration

### What This Module Imports

| Import          | Source        | Usage                                                                |
|-----------------|---------------|----------------------------------------------------------------------|
| `io`            | Python stdlib | `io.BytesIO` — wraps raw bytes into a file-like object for pandas.  |
| `pandas` (`pd`) | Third-party   | `pd.read_csv`, `pd.DataFrame` — core CSV parsing and data structure. |

### Runtime Requirements

- **Python ≥ 3.10** — the `str | None` union type hint syntax (PEP 604) requires Python 3.10 or later. Using this module on earlier Python versions will raise a `TypeError` at import time.
- **`pandas`** must be installed in the environment (it is not part of the Python standard library).

### What Depends on This Module

According to the module docstring, the intended consumers are:

- **Batch endpoints** — endpoints that accept bulk CSV uploads for processing multiple reviews at once.
- **Report endpoints** — endpoints that generate analytical reports from uploaded review data.

These endpoints are expected to call `parse_csv_bytes` to obtain a DataFrame from uploaded content, then pass that DataFrame to `detect_review_column` to determine which column to feed into downstream processing (e.g., sentiment analysis, NLP pipelines).

### Integration Pattern (Expected Usage)

```python
from api.csv_utils import parse_csv_bytes, detect_review_column

# Inside an endpoint handler:
df = parse_csv_bytes(uploaded_file_contents)
review_col = detect_review_column(df, hint=request.query_params.get("review_column"))
reviews = df[review_col].dropna().tolist()
# ... pass reviews to business logic
```

### Error Handling Guidance for Consumers

Endpoint handlers should be prepared to catch the following exceptions surfaced by this module:

| Exception   | Source                                         | Recommended Handling                                                                      |
|-------------|------------------------------------------------|-------------------------------------------------------------------------------------------|
| `ValueError` | `detect_review_column` (no column identified) | Return HTTP 400 with the exception message; it is already user-readable.                 |
| `Exception`  | `parse_csv_bytes` (both encoding attempts fail) | Return HTTP 422 or 400 indicating the file could not be parsed as a valid CSV.          |

Note that `parse_csv_bytes` only re-raises from the **second** (`latin-1`) attempt. A failure in the UTF-8 attempt alone is silently swallowed and retried; only a failure in both attempts surfaces to the caller.

---

`FUNCTIONAL_CHANGE: YES`
