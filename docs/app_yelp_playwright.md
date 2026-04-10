# `app/yelp_playwright.py` — Technical Documentation

---

## 1. Module Overview

### Purpose

`yelp_playwright.py` implements a headless-browser-based scraper for extracting customer reviews from Yelp business pages. It uses [Playwright](https://playwright.dev/python/) to control a real Chromium browser, enabling it to handle Yelp's JavaScript-rendered content and basic bot-detection measures that would defeat simple HTTP-based scrapers.

### Responsibilities

- Launching and managing a headless Chromium browser session with anti-detection configurations.
- Navigating to a Yelp business page and extracting the business name.
- Iterating through paginated review pages (up to a configurable maximum).
- Extracting per-review data: review text, star rating, and date.
- Returning structured review records as a list of Python dictionaries.
- Enforcing a hard pagination cap to prevent runaway scraping sessions.

### Where It Fits in the System

This module acts as a **data acquisition layer** for Yelp-sourced review data. It is designed to be called by higher-level application code (e.g., an API endpoint, a data pipeline, or a CLI tool) that needs raw review content from Yelp. The output list of dictionaries can be passed downstream for storage, sentiment analysis, or further processing. It is one of potentially several scraper modules (e.g., Google Reviews, TripAdvisor) that share a common output schema.

---

## 2. Key Components

### Public Functions

---

#### `scrape_yelp_reviews_playwright`

```python
def scrape_yelp_reviews_playwright(url: str, max_reviews: int = 100) -> list[dict]:
```

**Description**

The sole public entry point of this module. Launches a headless Chromium browser via Playwright's synchronous API, navigates to the given Yelp business URL, and scrapes reviews across one or more paginated pages. Returns a list of review dictionaries, stopping when either `max_reviews` has been collected, no further reviews are found, or the pagination safety cap is hit.

---

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | *(required)* | Full Yelp business URL. Query parameters are automatically stripped; only the base business path is used. Example: `https://www.yelp.com/biz/some-business-name` |
| `max_reviews` | `int` | `100` | Maximum number of review records to collect before stopping. Must be a positive integer. |

---

**Return Value**

Returns a `list[dict]`. Each dictionary represents a single review and conforms to the following schema:

```python
{
    'business_name': str,        # Extracted from the page's <h1> element; empty string if unavailable
    'review_text':   str,        # The body text of the review (always >= 20 characters)
    'rating':        int | None, # Star rating as an integer (1–5), or None if not found
    'review_date':   str | None, # Human-readable date string (e.g., "10/15/2023"), or None if not found
    'source':        str,        # Always the literal string "yelp"
}
```

Returns an empty list (`[]`) if no reviews could be found or the page could not be loaded.

---

**Behavior & Internal Logic**

The function proceeds in the following stages:

1. **URL Normalization**
   Any query string is stripped from the input URL using `url.split('?')[0]`, ensuring the scraper always begins from the first page of reviews.

2. **Browser Initialization**
   A headless Chromium browser is launched with two flags:
   - `--disable-blink-features=AutomationControlled`: Suppresses the `navigator.webdriver` flag that browser-fingerprinting scripts look for.
   - `--no-sandbox`: Required in containerized or restricted environments (e.g., Docker).

   A browser context is created with:
   - A realistic macOS/Chrome user-agent string to reduce bot-detection likelihood.
   - `locale="en-US"` to ensure English-language content is served.

3. **WebDriver Concealment**
   An init script is injected into every new page:
   ```javascript
   Object.defineProperty(navigator, 'webdriver', {get: () => undefined})
   ```
   This further obscures the automated nature of the browser from JavaScript-based detection.

4. **Business Name Extraction**
   The scraper navigates to the base URL, waits up to 10 seconds for an `<h1>` element, and extracts its text as `business_name`. Failures are silently swallowed.

5. **Pagination Loop**
   Yelp displays 10 reviews per page, offset via the `?start=N` query parameter. The loop:
   - Starts at `page_num = 0` (no `?start=` suffix on the first page).
   - Increments `page_num` after each page, navigating to `?start=10`, `?start=20`, etc.
   - Breaks if no review content is found within 15 seconds.
   - Hard-stops at `page_num >= 15` (i.e., a maximum of 150 candidate reviews across 15 pages).

6. **Review Extraction — Primary Path**
   Review container elements are selected using:
   ```
   li[class*="margin-b"][class*="padding-b"], div[class*="review__"]
   ```
   For each container:
   - **Review text** is extracted from `p.comment__09f24__D0cxf` or `p[lang]`. Reviews with text shorter than 20 characters are skipped.
   - **Star rating** is parsed from the `aria-label` attribute of `div[aria-label*="star rating"]` using a regex (`r'(\d)'`). Returns an `int` or `None`.
   - **Date** is extracted from `span.css-chan6m0`. Returns a string or `None`.

7. **Review Extraction — Fallback Path**
   If no container elements are found (e.g., due to a Yelp DOM structure change), the scraper falls back to directly querying:
   ```
   p.comment__09f24__D0cxf, p[lang="en"]
   ```
   In this fallback mode, `rating` and `review_date` are always `None` since container context is unavailable.

8. **Early Termination**
   The loop breaks early if:
   - A page yields no reviews matching the minimum length filter (`page_had_reviews` remains `False`).
   - The `max_reviews` count is reached.
   - The selector wait times out (page structure not recognized).

9. **Cleanup**
   `browser.close()` is called explicitly before the function returns. The `with sync_playwright() as p:` context manager also ensures Playwright infrastructure is torn down.

---

**Side Effects**

- Launches a real Chromium subprocess (resource-intensive).
- Makes live HTTP requests to `www.yelp.com`. Subject to Yelp's rate limiting, bot detection, and terms of service.
- No state is written to disk; all data is held in memory.

**Dependencies**

- `playwright.sync_api.sync_playwright` — must be installed (`pip install playwright`) and browsers must be installed (`playwright install chromium`).
- `re` (standard library) — imported inline inside the loop for rating extraction.

---

**Usage Example**

```python
from app.yelp_playwright import scrape_yelp_reviews_playwright

reviews = scrape_yelp_reviews_playwright(
    url="https://www.yelp.com/biz/gary-danko-san-francisco",
    max_reviews=50,
)

for review in reviews:
    print(review['rating'], review['review_text'][:80])
```

---

### Internal Constants / Magic Values

These are not exported but are significant for maintainers:

| Value | Location | Meaning |
|---|---|---|
| `15` | Pagination loop | Maximum pages scraped per call (~150 review candidates) |
| `10` | Pagination offset | Yelp's reviews-per-page count |
| `20` | Text filter | Minimum character length for a review to be accepted |
| `60000` | `page.goto` timeout | 60-second navigation timeout (milliseconds) |
| `15000` | `wait_for_selector` | 15-second timeout waiting for review content |
| `10000` | Business name wait | 10-second timeout for `<h1>` to appear |

---

## 3. What Changed

This file was **newly introduced** in this commit (git status: `new file mode 100644`). There is no prior version of this module; the diff represents a net addition of 138 lines establishing the module from scratch.

### What Was Added

#### Entire Module — Initial Implementation

The complete `yelp_playwright.py` file was created, providing:

1. **A new scraping strategy using Playwright**: Prior to this commit, no Playwright-based Yelp scraper existed in this path. This represents either a replacement for a simpler HTTP-based scraper or a brand-new capability in the project.

2. **Anti-detection measures**: The implementation includes deliberate choices to avoid Yelp's bot-detection:
   - Custom user-agent string mimicking a real macOS Chrome browser.
   - `--disable-blink-features=AutomationControlled` launch argument.
   - `navigator.webdriver` property suppression via init script.
   
   These measures are functionally significant — without them, Yelp would likely serve CAPTCHAs or empty pages.

3. **A two-path extraction strategy**: The primary container-based extractor with full metadata (rating, date) and a fallback text-only extractor makes the scraper more resilient to minor DOM changes on Yelp's side.

4. **Pagination support**: The scraper handles Yelp's `?start=N` pagination scheme, enabling bulk collection beyond a single page's 10 reviews.

5. **A bounded execution model**: The `page_num >= 15` guard and `max_reviews` parameter together ensure the scraper never runs indefinitely, making it safe to call in automated pipelines.

### Why This Change Matters Functionally

Playwright-based scraping is qualitatively different from `requests`/`httpx`-based scraping:
- JavaScript must execute fully for Yelp's review content to appear in the DOM. A plain HTTP client would receive a nearly empty HTML shell. Playwright solves this by running a real browser.
- The anti-detection setup means the scraper is far more likely to successfully retrieve review data in production compared to a naive automation approach.

### Behavioral Differences from Before

Since this is a new file, there is no prior behavior to compare against. From the system's perspective, the functional change is that the capability to scrape Yelp reviews via a browser automation approach now exists where it did not before.

---

## 4. Dependencies & Integration

### What This Module Imports

| Import | Source | Usage |
|---|---|---|
| `sync_playwright` | `playwright.sync_api` (third-party) | Core browser automation API |
| `re` | Python standard library | Parsing star rating from `aria-label` strings (imported inline) |

### Runtime Requirements

- **Playwright Python package**: `pip install playwright`
- **Chromium browser binary**: `playwright install chromium`
- **Network access**: Live outbound HTTPS to `www.yelp.com`
- **System resources**: Each call spawns a Chromium subprocess. Memory and CPU usage are substantially higher than HTTP-only scrapers.

### What May Depend on This Module

Based on the output schema and naming convention, the following types of consumers are anticipated:

- **API route handlers** (e.g., FastAPI/Flask endpoints) that accept a Yelp URL and return scraped reviews as JSON.
- **Data pipeline scripts** that aggregate reviews from multiple sources (Yelp, Google, etc.) using a shared `list[dict]` schema with the `source` field as a discriminator.
- **CLI tools** that invoke this function directly with a URL argument.
- **Storage/ORM layers** that persist the returned dictionaries to a database, relying on the stable key names (`business_name`, `review_text`, `rating`, `review_date`, `source`).

### Integration Notes

- The function is **synchronous** and **blocking**. Calling it inside an async web framework (e.g., FastAPI) requires running it in a thread pool executor (`asyncio.to_thread` or `loop.run_in_executor`) to avoid blocking the event loop.
- The `import re` statement inside the loop body is a minor code quality issue — it should ideally be at the module level. Python caches module imports so this has no runtime performance impact, but it may confuse linters and is inconsistent with Python conventions.
- CSS class selectors such as `comment__09f24__D0cxf` and `css-chan6m0` are **generated/hashed class names** that Yelp may change with any frontend deployment. These selectors will silently degrade (returning `None` for affected fields) rather than raising exceptions, which is a deliberate defensive choice.

---

`FUNCTIONAL_CHANGE: YES`
