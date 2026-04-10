# `app/scraper_service.py` — Technical Documentation

---

## 1. Module Overview

`scraper_service.py` is the **service layer** responsible for orchestrating review scraping from multiple sources within the application. It acts as the bridge between higher-level application logic (e.g., a FastAPI route handler) and the lower-level, source-specific scraping backends.

### Purpose

The module provides a clean, stable interface for three categories of operation:

1. **URL parsing** — extracting canonical identifiers from source-specific URLs (currently: IMDB title IDs).
2. **Source detection** — automatically determining which scraping backend to dispatch to based on URL structure.
3. **Review scraping** — fetching and returning structured review data from IMDB, Google Maps, or Yelp.

Scraping is performed via **Playwright (headless Chromium)** through source-specific backend modules (`app.imdb_playwright`, `app.google_playwright`, `app.yelp_playwright`).

### Responsibilities

| Responsibility | Function |
|---|---|
| Parse and validate an IMDB URL to extract a canonical movie ID | `extract_movie_id` |
| Detect the review source from any supported URL | `detect_source` |
| Dispatch scraping to the correct backend based on URL source | `scrape_reviews` |
| Delegate IMDB-specific review scraping to the Playwright backend | `scrape_imdb_reviews` |

### Position in the System

```
FastAPI Route Handler
       │
       ▼
scraper_service.py                  ← YOU ARE HERE
  ├── extract_movie_id()            (URL parsing utility)
  ├── detect_source()               (source detection)
  ├── scrape_reviews()              (unified entry point / dispatcher)
  │        ├── scrape_imdb_reviews()
  │        │          │
  │        │          ▼
  │        │   app/imdb_playwright.py
  │        │   scrape_imdb_reviews_playwright()
  │        │   (Playwright + headless Chromium → IMDB)
  │        │
  │        ├── app/google_playwright.py
  │        │   scrape_google_reviews_playwright()
  │        │   (Playwright + headless Chromium → Google Maps)
  │        │
  │        └── app/yelp_playwright.py
  │            scrape_yelp_reviews_playwright()
  │            (Playwright + headless Chromium → Yelp)
  │
  └──────────────────────────────────────────
                    │
                    ▼
            list[dict] of reviews
```

---

## 2. Key Components

### 2.1 `extract_movie_id`

```python
def extract_movie_id(imdb_url: str) -> str:
```

#### Description

Parses an IMDB URL (or any string) and extracts the **IMDB title ID** — a token matching the pattern `tt` followed by one or more digits (e.g., `tt1375666`).

The function uses a regular expression search rather than strict URL parsing, so it tolerates a variety of input formats (full URLs, path-only strings, bare IDs) as long as the `tt\d+` pattern appears somewhere in the input.

#### Parameters

| Parameter | Type | Description |
|---|---|---|
| `imdb_url` | `str` | Any string expected to contain an IMDB title ID in the format `tt<digits>`. Typically a full IMDB URL such as `https://www.imdb.com/title/tt1375666/`. |

#### Return Value

| Type | Description |
|---|---|
| `str` | The matched IMDB title ID, e.g. `"tt1375666"`. |

#### Raises

| Exception | Condition |
|---|---|
| `ValueError` | Raised when the input string does not contain a pattern matching `tt\d+`. The error message includes the original input for diagnostics. |

#### Side Effects / Dependencies

- No I/O, no network access.
- Depends only on the standard library `re` module.
- Pure function; safe to call from any context including async code.

#### Example

```python
extract_movie_id("https://www.imdb.com/title/tt1375666/reviews")
# Returns: "tt1375666"

extract_movie_id("not-a-valid-url")
# Raises: ValueError("Invalid IMDB URL: could not find a title ID (tt...) in 'not-a-valid-url'")
```

---

### 2.2 `detect_source`

```python
def detect_source(url: str) -> str:
```

#### Description

Inspects a URL string and determines which supported review source it belongs to. Detection is performed via **case-insensitive substring matching** against known URL patterns for each supported platform.

This function is used internally by `scrape_reviews` to determine which backend to dispatch to, but it is also a public utility that callers can invoke independently for pre-validation or routing decisions.

#### Supported Patterns

| Source | Matched URL Patterns |
|---|---|
| `"imdb"` | Contains `imdb.com/title/tt` |
| `"google"` | Contains `google.com/maps`, `goo.gl/maps`, or `maps.app.goo.gl` |
| `"yelp"` | Contains `yelp.com/biz/` |

#### Parameters

| Parameter | Type | Description |
|---|---|---|
| `url` | `str` | A URL string to inspect. The check is case-insensitive. |

#### Return Value

| Type | Description |
|---|---|
| `str` | One of `"imdb"`, `"google"`, or `"yelp"` — identifying the detected review source. |

#### Raises

| Exception | Condition |
|---|---|
| `ValueError` | Raised when the URL does not match any supported source pattern. The message instructs the caller to provide a link from IMDB, Google Maps, or Yelp. |

#### Side Effects / Dependencies

- No I/O, no network access.
- Pure function; depends only on built-in Python string operations.
- Safe to call from any context including async code.

#### Example

```python
detect_source("https://www.imdb.com/title/tt1375666/reviews")
# Returns: "imdb"

detect_source("https://www.google.com/maps/place/Some+Restaurant")
# Returns: "google"

detect_source("https://www.yelp.com/biz/some-business-name")
# Returns: "yelp"

detect_source("https://maps.app.goo.gl/abc123")
# Returns: "google"

detect_source("https://www.tripadvisor.com/")
# Raises: ValueError("Unsupported URL. Please provide a link from IMDB, Google Maps, or Yelp.")
```

---

### 2.3 `scrape_reviews`

```python
def scrape_reviews(url: str, max_reviews: int = 100) -> list[dict]:
```

#### Description

The **unified, source-agnostic entry point** for scraping reviews. Callers provide any supported URL; this function automatically detects the source via `detect_source`, routes to the appropriate backend, and returns a normalized list of review dicts.

- For IMDB URLs, it first calls `extract_movie_id` to parse the title ID, then delegates to `scrape_imdb_reviews`.
- For Google Maps URLs, it lazily imports and calls `scrape_google_reviews_playwright` from `app.google_playwright`.
- For Yelp URLs, it lazily imports and calls `scrape_yelp_reviews_playwright` from `app.yelp_playwright`.

All three backend imports are **lazy** (performed inside the function body), keeping the module importable in environments where Playwright is not installed.

#### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | *(required)* | A full URL pointing to a supported review source (IMDB, Google Maps, or Yelp). |
| `max_reviews` | `int` | `100` | The maximum number of reviews to scrape. Passed directly to whichever backend is dispatched. |

#### Return Value

| Type | Description |
|---|---|
| `list[dict]` | A list of review dictionaries. All dicts include a common set of keys; additional source-specific keys may also be present. |

#### Common Review Dict Keys

| Key | Type | Description |
|---|---|---|
| `review_text` | `str` | The full text body of the review. |
| `rating` | `str` or `None` | The numeric rating given by the reviewer, if present. |
| `review_date` | `str` | The date the review was posted. |
| `source` | `str` | The origin of the review (e.g., `"imdb"`, `"google"`, `"yelp"`). |

Additional source-specific keys (e.g., `movie_title`, `business_name`) may be present depending on the backend. Refer to each backend module's documentation for the full per-source schema.

#### Raises

| Exception | Condition |
|---|---|
| `ValueError` | Propagated from `detect_source` if the URL is not supported. |
| `ValueError` | Propagated from `extract_movie_id` if the IMDB URL does not contain a valid title ID. |
| Other | Any exceptions raised by the underlying Playwright backends propagate to the caller without interception. |

#### Side Effects / Dependencies

- **Performs network I/O** via whichever Playwright backend is dispatched.
- **Lazily imports** `app.google_playwright` and `app.yelp_playwright` at call time; `app.imdb_playwright` is lazily imported inside `scrape_imdb_reviews`.
- Blocking and synchronous from the caller's perspective. Should be wrapped in `asyncio.run_in_executor` or a thread pool if invoked from an `async` FastAPI route to avoid blocking the event loop.

#### Example

```python
# IMDB
reviews = scrape_reviews("https://www.imdb.com/title/tt1375666/", max_reviews=50)

# Google Maps
reviews = scrape_reviews("https://www.google.com/maps/place/Some+Restaurant", max_reviews=30)

# Yelp
reviews = scrape_reviews("https://www.yelp.com/biz/some-business", max_reviews=20)

# Unsupported URL
reviews = scrape_reviews("https://www.tripadvisor.com/")
# Raises: ValueError("Unsupported URL. Please provide a link from IMDB, Google Maps, or Yelp.")
```

---

### 2.4 `scrape_imdb_reviews`

```python
def scrape_imdb_reviews(
    movie_id: str,
    max_reviews: int = 100,
) -> list[dict]:
```

#### Description

An IMDB-specific scraping function that delegates directly to `scrape_imdb_reviews_playwright` from `app.imdb_playwright`, which drives a headless Chromium browser via Playwright to fetch and parse review data from IMDB.

This function is called internally by `scrape_reviews` when an IMDB URL is detected, but it is also a valid public entry point for callers that already have a canonical movie ID and want to bypass URL parsing.

The import of `app.imdb_playwright` is performed **lazily** (inside the function body) rather than at module load time, keeping the module importable in environments where Playwright is not installed.

#### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `movie_id` | `str` | *(required)* | A valid IMDB title ID (e.g., `"tt1375666"`). Typically obtained via `extract_movie_id()`. |
| `max_reviews` | `int` | `100` | The maximum number of reviews to scrape. Passed directly to the Playwright backend. |

#### Return Value

| Type | Description |
|---|---|
| `list[dict]` | A list of review dictionaries, one per scraped review. |

#### Review Dict Schema (IMDB-specific)

| Key | Type | Description |
|---|---|---|
| `movie_id` | `str` | The IMDB title ID (e.g., `"tt1375666"`). |
| `movie_title` | `str` | The title of the movie as reported by IMDB. |
| `review_text` | `str` | The full text body of the review. |
| `rating` | `str` or `None` | The numeric rating given by the reviewer, if present. |
| `review_date` | `str` | The date the review was posted. |
| `source` | `str` | Always `"imdb"`. |

#### Raises

Exceptions are not explicitly caught here; any exceptions raised by `scrape_imdb_reviews_playwright` propagate directly to the caller. Refer to `app/imdb_playwright.py` for the specific failure modes of the Playwright backend.

#### Side Effects / Dependencies

- **Performs network I/O** by connecting to `www.imdb.com` via the Playwright backend.
- **Lazily imports** `app.imdb_playwright` at call time, not at module load time.
- Blocking and synchronous from the caller's perspective. Should be wrapped in `asyncio.run_in_executor` or a thread pool if invoked from an `async` FastAPI route.

#### Example

```python
movie_id = extract_movie_id("https://www.imdb.com/title/tt1375666/")
reviews = scrape_imdb_reviews(movie_id, max_reviews=50)
# Returns:
# [
#   {
#     "movie_id": "tt1375666",
#     "movie_title": "Inception",
#     "review_text": "A mind-bending thriller...",
#     "rating": "9",
#     "review_date": "2010-07-20",
#     "source": "imdb"
#   },
#   ...
# ]
```

---

## 3. What Changed

### Summary

This commit expands the module's scope from **IMDB-only** to **multi-source** review scraping. Two new public functions were added (`detect_source` and `scrape_reviews`), and the module's docstring was updated to reflect the broader responsibility. No existing functions were modified.

### Additions

#### New function: `detect_source(url: str) -> str`

A new pure utility function that inspects a URL string and returns a string token identifying the review source (`"imdb"`, `"google"`, or `"yelp"`). It raises `ValueError` for any URL that does not match a supported pattern.

This function encapsulates all source-detection logic in one testable, reusable place, ensuring that routing decisions are not scattered across callers.

#### New function: `scrape_reviews(url: str, max_reviews: int = 100) -> list[dict]`

A new unified dispatcher that serves as a **single entry point for all review scraping**, regardless of source. Before this change, callers had to:

1. Know which source the URL belonged to.
2. Call `extract_movie_id` themselves for IMDB URLs.
3. Import and call the correct backend directly.

After this change, callers provide only a URL and optionally `max_reviews`; the module handles detection and dispatch internally. This is a significant improvement in the public API's ergonomics.

#### Updated module docstring

```diff
-Service layer for scraping movie reviews.
+Service layer for scraping reviews from various sources.
```

Reflects the expanded scope of the module.

### What Was Not Changed

- `extract_movie_id` — unchanged in signature and behavior.
- `scrape_imdb_reviews` — unchanged in signature, behavior, and defaults. The `max_reviews` default of `100` was already in place before this diff.

### Why the Changes Matter Functionally

| Impact Area | Before | After |
|---|---|---|
| Supported sources | IMDB only | IMDB, Google Maps, Yelp |
| Caller burden for routing | Caller must detect source and call correct backend | `scrape_reviews` handles detection and dispatch automatically |
| Public API surface | `extract_movie_id`, `scrape_imdb_reviews` | `extract_movie_id`, `detect_source`, `scrape_reviews`, `scrape_imdb_reviews` |
| Google Maps scraping | Not available through this module | Available via `scrape_reviews` → `app.google_playwright` |
| Yelp scraping | Not available through this module | Available via `
