# `app/google_playwright.py` — Technical Documentation

---

## 1. Module Overview

### Purpose

`google_playwright.py` implements a **headless-browser-based scraper** for extracting customer reviews from Google Maps business pages. It uses [Playwright](https://playwright.dev/python/) to automate a real Chromium browser instance, enabling it to interact with Google Maps' JavaScript-rendered UI — something that static HTTP request approaches cannot reliably accomplish.

### Responsibilities

- Accept a Google Maps URL (in several supported formats) and navigate to the corresponding business page.
- Automatically resolve search result pages and short links to a specific business detail page.
- Locate and click the **Reviews tab** to surface the review feed.
- Incrementally scroll the reviews panel to trigger lazy-loading of additional reviews.
- Expand truncated ("More") review text to capture full content.
- Parse and return structured review data (text, star rating, date, business name) as a list of dictionaries.

### Position in the System

This module sits in the **data ingestion layer** (`app/`) and is responsible for one specific data source: Google Maps. It is a self-contained scraping unit — callers provide a URL and a review cap, and receive a normalized list of review records. It is expected to be invoked by higher-level orchestration code (e.g., a task runner, API endpoint, or CLI command) that aggregates reviews from multiple sources.

---

## 2. Key Components

### Function: `scrape_google_reviews_playwright`

```python
def scrape_google_reviews_playwright(url: str, max_reviews: int = 100) -> list[dict]:
```

#### What It Does

Launches a headless Chromium browser, navigates to the provided Google Maps URL, and scrapes up to `max_reviews` customer reviews from the business's review feed. Returns the collected reviews as a list of structured dictionaries.

The function handles the full lifecycle of the browser session: launch, navigation, interaction, extraction, and cleanup.

#### Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `url` | `str` | *(required)* | A Google Maps URL pointing to a business. Supports `/maps/place/...`, `/maps/search/...`, and `maps.app.goo.gl/...` short-link formats. |
| `max_reviews` | `int` | `100` | The maximum number of reviews to collect. Scrolling stops early once this threshold is reached. |

#### Return Value

Returns a `list[dict]`. Each dictionary represents one review and contains the following keys:

| Key | Type | Description |
|---|---|---|
| `"business_name"` | `str` | The name of the business as extracted from the page `<h1>` element, or the page title as fallback. |
| `"review_text"` | `str` | The full text of the review (after expansion of truncated content). |
| `"rating"` | `int` \| `None` | Star rating (1–5) parsed from the `aria-label` of the rating element, or `None` if not found. |
| `"review_date"` | `str` \| `None` | The relative or absolute date string as displayed on Google Maps (e.g., `"2 months ago"`), or `None` if not found. |
| `"source"` | `str` | Always `"google"`. Identifies the data source for downstream consumers. |

Reviews with missing text or text shorter than 10 characters are **silently skipped**.

#### Side Effects

- Spawns and terminates a Chromium browser subprocess.
- Makes real HTTP requests to Google Maps servers.
- Introduces deliberate timing delays (`wait_for_timeout`) to mimic human browsing behaviour and allow JavaScript rendering.

#### Early Return Conditions

The function returns an empty list (`[]`) without raising an exception in these cases:

1. **No Reviews tab found** — the page does not contain a `button[role="tab"]` element whose text includes `"review"`.
2. **No review containers rendered** — after clicking the Reviews tab, no `div[data-review-id]` elements appear within 10 seconds.

#### Internal Behaviour (Step-by-Step)

```
1. Launch headless Chromium with anti-detection flags.
2. Create a browser context with a realistic User-Agent, en-US locale,
   and 1280×900 viewport.
3. Inject an init script to hide the `navigator.webdriver` property.
4. Navigate to `url`; wait for DOM content + 5 s settling delay.
5. Detect search results pages: if the first <h1> reads "Results" or
   no tab buttons exist, click the first `/maps/place` link found.
6. Extract business name from <h1>; fall back to page title.
7. Find and click the "Reviews" tab button; wait 3 s.
8. Wait up to 10 s for `div[data-review-id]` containers to appear.
9. Locate the scrollable reviews panel via a cascade of CSS selectors.
10. Iteratively scroll the panel (up to 50 iterations × 1.5 s waits),
    stopping when `max_reviews` are loaded or 3 consecutive scrolls
    yield no new reviews (stall detection).
11. Click all "More" expand buttons to unfurl truncated review text.
12. Iterate over containers (up to `max_reviews`), extracting text,
    rating, and date via targeted CSS selectors.
13. Close the browser and return collected reviews.
```

#### CSS Selectors Used

| Data Point | Primary Selector | Fallback Selector |
|---|---|---|
| Review text | `span.wiI7pd` | `div.MyEned span` |
| Star rating | `span.kvMYJc[aria-label]` | *(none)* |
| Review date | `span.rsqaWe` | *(none)* |
| Scrollable panel | `div.m6QErb.DxyBCb.kA9KIf.dS8AEf[role="feed"]` | `div.m6QErb.DxyBCb.kA9KIf.dS8AEf` → `div.m6QErb.DxyBCb` |
| Expand buttons | `div[data-review-id] button.w8nwRe.kyuRq` | `div[data-review-id] button.M77dve` |

> ⚠️ **Fragility Notice:** These selectors target obfuscated Google Maps CSS class names that are subject to change without notice during Google's periodic frontend deployments.

---

## 3. What Changed

This is a **new file** — the entire module was introduced in this commit. There is no prior version to diff against; all content represents net-new additions.

### What Was Added

#### The module itself (`app/google_playwright.py`)
A complete, production-ready scraper module was added from scratch, comprising:

- **Module-level docstring** documenting the three accepted URL formats.
- **`scrape_google_reviews_playwright` function** (157 lines) implementing the full scraping pipeline described above.

### Why This Change Matters Functionally

Prior to this commit, the project had no capability to collect reviews from Google Maps. This module introduces:

1. **A new data source integration** — Google Maps reviews can now be ingested into the system alongside any existing sources.
2. **Anti-detection measures** — the scraper is explicitly designed to avoid triggering Google's bot-detection mechanisms by:
   - Disabling the `AutomationControlled` Blink feature flag.
   - Overriding `navigator.webdriver` via an init script.
   - Using a realistic, versioned Chrome User-Agent string.
3. **Robust URL handling** — the scraper handles three distinct Google Maps URL formats, including short links and search results pages, making it resilient to a variety of input sources.
4. **Lazy-load handling** — the scroll loop with stall detection ensures that paginated/lazy-loaded reviews are fetched up to the requested cap, rather than only the initially visible set.
5. **Full review text** — the "More" button expansion step ensures truncated reviews are captured in their entirety.

### Behavioral Differences From Before

| Aspect | Before | After |
|---|---|---|
| Google Maps review collection | Not possible | Supported |
| Accepted URL formats | N/A | 3 formats (place, search, short link) |
| Review cap | N/A | Configurable via `max_reviews` (default 100) |
| Anti-bot evasion | N/A | User-Agent spoofing, `webdriver` hiding |

---

## 4. Dependencies & Integration

### External Dependencies

| Dependency | Import | Purpose |
|---|---|---|
| `playwright` | `from playwright.sync_api import sync_playwright` | Drives the headless Chromium browser; must be installed via `pip install playwright` and browsers provisioned with `playwright install chromium`. |
| `re` *(stdlib)* | `import re` | Used to extract the numeric star rating from an `aria-label` attribute string via `re.search(r"(\d)", aria)`. |

### Runtime Requirements

- **Chromium binary**: Must be installed separately via `playwright install chromium`. The function will raise a `playwright` exception at launch time if Chromium is not available.
- **Network access**: The scraping function makes outbound HTTPS requests to `google.com` and potentially `maps.app.goo.gl` for short-link resolution.

### What Depends on This Module

This module exposes a single public function intended to be called by:

- **Orchestration / task layer**: Any module responsible for coordinating multi-source review scraping would import and call `scrape_google_reviews_playwright`.
- **API endpoints**: A web API handler (e.g., FastAPI route) could call this function in response to a user-submitted Google Maps URL.
- **CLI scripts**: Command-line entry points for batch scraping jobs.

### Integration Example

```python
from app.google_playwright import scrape_google_reviews_playwright

reviews = scrape_google_reviews_playwright(
    url="https://www.google.com/maps/place/Some+Business/@...",
    max_reviews=50,
)

for review in reviews:
    print(review["business_name"], review["rating"], review["review_text"])
```

### Notes for Integrators

- The function is **synchronous and blocking**. It should be run in a thread pool or separate process if called from an async web framework.
- Execution time is variable and can be **30–120+ seconds** depending on network speed and `max_reviews`. Plan timeouts accordingly.
- The function **never raises exceptions** for scraping failures (missing tab, no reviews rendered) — it returns an empty list. Callers should check the length of the returned list to detect failures.
- The `"source": "google"` field in every returned record enables downstream consumers to route or filter records by origin without additional metadata.

---

`FUNCTIONAL_CHANGE: YES`
