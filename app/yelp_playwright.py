"""
Playwright-based Yelp review scraper.

Expects a Yelp business URL like:
  https://www.yelp.com/biz/some-business-name
"""
from playwright.sync_api import sync_playwright


def scrape_yelp_reviews_playwright(url: str, max_reviews: int = 100) -> list[dict]:
    reviews = []

    # Normalize URL — strip query params, ensure we start at page 1
    base_url = url.split('?')[0]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Extract business name
        business_name = ""
        page.goto(base_url, wait_until="domcontentloaded", timeout=60000)

        try:
            page.wait_for_selector('h1', timeout=10000)
            h1 = page.query_selector('h1')
            if h1:
                business_name = h1.inner_text().strip()
        except Exception:
            pass

        # Yelp paginates reviews 10 per page
        page_num = 0
        while len(reviews) < max_reviews:
            if page_num > 0:
                paginated_url = f"{base_url}?start={page_num * 10}"
                page.goto(paginated_url, wait_until="domcontentloaded", timeout=60000)

            # Wait for review content
            try:
                page.wait_for_selector(
                    '#reviews p.comment__09f24__D0cxf, '
                    'div[class*="review"] p[lang], '
                    'li[class*="margin-b"] p.comment__09f24__D0cxf, '
                    'section[aria-label="Recommended Reviews"] p[lang]',
                    timeout=15000,
                )
            except Exception:
                break

            # Extract reviews from this page
            containers = page.query_selector_all(
                'li[class*="margin-b"][class*="padding-b"],'
                'div[class*="review__"]'
            )

            if not containers:
                # Fallback: try to find review paragraphs directly
                paragraphs = page.query_selector_all(
                    'p.comment__09f24__D0cxf, p[lang="en"]'
                )
                for p_el in paragraphs:
                    text = p_el.inner_text().strip()
                    if text and len(text) >= 20:
                        reviews.append({
                            'business_name': business_name,
                            'review_text': text,
                            'rating': None,
                            'review_date': None,
                            'source': 'yelp',
                        })
                        if len(reviews) >= max_reviews:
                            break
            else:
                page_had_reviews = False
                for container in containers:
                    # Review text
                    text_el = container.query_selector(
                        'p.comment__09f24__D0cxf, p[lang]'
                    )
                    review_text = text_el.inner_text().strip() if text_el else None

                    if not review_text or len(review_text) < 20:
                        continue

                    page_had_reviews = True

                    # Star rating
                    rating = None
                    stars_el = container.query_selector(
                        'div[aria-label*="star rating"]'
                    )
                    if stars_el:
                        aria = stars_el.get_attribute('aria-label') or ''
                        import re
                        m = re.search(r'(\d)', aria)
                        if m:
                            rating = int(m.group(1))

                    # Date
                    date_el = container.query_selector('span.css-chan6m0')
                    review_date = date_el.inner_text().strip() if date_el else None

                    reviews.append({
                        'business_name': business_name,
                        'review_text': review_text,
                        'rating': rating,
                        'review_date': review_date,
                        'source': 'yelp',
                    })

                    if len(reviews) >= max_reviews:
                        break

                if not page_had_reviews:
                    break

            page_num += 1

            # Safety: don't paginate too many times
            if page_num >= 15:
                break

        browser.close()

    return reviews
