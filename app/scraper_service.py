"""
Service layer for scraping reviews from various sources.
"""
import re


def extract_movie_id(imdb_url: str) -> str:
    """Extract IMDB title ID (e.g. 'tt1375666') from a URL."""
    match = re.search(r"(tt\d+)", imdb_url)
    if not match:
        raise ValueError(
            f"Invalid IMDB URL: could not find a title ID (tt...) in '{imdb_url}'"
        )
    return match.group(1)


def detect_source(url: str) -> str:
    """Detect the review source from a URL. Returns 'imdb', 'google', 'yelp', or raises."""
    url_lower = url.lower()
    if "imdb.com/title/tt" in url_lower:
        return "imdb"
    if "google.com/maps" in url_lower or "goo.gl/maps" in url_lower or "maps.app.goo.gl" in url_lower:
        return "google"
    if "yelp.com/biz/" in url_lower:
        return "yelp"
    raise ValueError(
        "Unsupported URL. Please provide a link from IMDB, Google Maps, or Yelp."
    )


def scrape_reviews(url: str, max_reviews: int = 100) -> list[dict]:
    """
    Scrape reviews from a URL. Auto-detects the source.

    Returns a list of review dicts with keys:
        review_text, rating, review_date, source,
        plus source-specific keys (movie_title, business_name, etc.)
    """
    source = detect_source(url)

    if source == "imdb":
        return scrape_imdb_reviews(extract_movie_id(url), max_reviews)
    elif source == "google":
        from app.google_playwright import scrape_google_reviews_playwright
        return scrape_google_reviews_playwright(url, max_reviews)
    elif source == "yelp":
        from app.yelp_playwright import scrape_yelp_reviews_playwright
        return scrape_yelp_reviews_playwright(url, max_reviews)
    else:
        raise ValueError(f"Unknown source: {source}")


def scrape_imdb_reviews(
    movie_id: str,
    max_reviews: int = 100,
) -> list[dict]:
    """
    Scrape IMDB reviews for a movie using Playwright (headless Chromium).

    Returns a list of review dicts with keys:
        movie_id, movie_title, review_text, rating, review_date, source
    """
    from app.imdb_playwright import scrape_imdb_reviews_playwright
    return scrape_imdb_reviews_playwright(movie_id, max_reviews)
