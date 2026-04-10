"""
Playwright-based Google Maps review scraper.

Accepts Google Maps URLs in any of these formats:
  - https://www.google.com/maps/place/Business+Name/...
  - https://www.google.com/maps/search/Business+Name/...
  - https://maps.app.goo.gl/...  (short links)
"""
import re
from playwright.sync_api import sync_playwright


def scrape_google_reviews_playwright(url: str, max_reviews: int = 100) -> list[dict]:
    reviews = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/131.0.0.0 Safari/537.36",
            locale="en-US",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # If this is a search results page, click the first place result
        results_links = page.query_selector_all('a[href*="/maps/place"]')
        if results_links:
            h1 = page.query_selector("h1")
            h1_text = h1.inner_text().strip() if h1 else ""
            if h1_text == "Results" or not page.query_selector_all('button[role="tab"]'):
                results_links[0].click()
                page.wait_for_timeout(4000)

        # Extract business name
        business_name = ""
        try:
            h1 = page.query_selector("h1")
            if h1:
                text = h1.inner_text().strip()
                if text and text != "Results":
                    business_name = text
        except Exception:
            pass

        if not business_name:
            business_name = page.title().replace(" - Google Maps", "").strip()

        # Click the Reviews tab
        tabs = page.query_selector_all('button[role="tab"]')
        reviews_tab_found = False
        for t in tabs:
            if "review" in t.inner_text().lower():
                t.click()
                page.wait_for_timeout(3000)
                reviews_tab_found = True
                break

        if not reviews_tab_found:
            browser.close()
            return reviews

        # Wait for review containers
        try:
            page.wait_for_selector("div[data-review-id]", timeout=10000)
        except Exception:
            browser.close()
            return reviews

        # Find the scrollable reviews panel (role="feed" or the known class pattern)
        scrollable = page.query_selector(
            'div.m6QErb.DxyBCb.kA9KIf.dS8AEf[role="feed"]'
        ) or page.query_selector(
            'div.m6QErb.DxyBCb.kA9KIf.dS8AEf'
        ) or page.query_selector(
            'div.m6QErb.DxyBCb'
        )

        # Scroll to load more reviews
        if scrollable:
            prev_count = 0
            stall_count = 0
            for _ in range(50):
                current = page.query_selector_all("div[data-review-id]")
                if len(current) >= max_reviews:
                    break
                scrollable.evaluate("el => el.scrollTop = el.scrollHeight")
                page.wait_for_timeout(1500)
                new_count = len(page.query_selector_all("div[data-review-id]"))
                if new_count == prev_count:
                    stall_count += 1
                    if stall_count >= 3:
                        break
                else:
                    stall_count = 0
                prev_count = new_count

        # Expand truncated reviews ("More" buttons inside review containers)
        more_buttons = page.query_selector_all(
            'div[data-review-id] button.w8nwRe.kyuRq, '
            'div[data-review-id] button.M77dve'
        )
        for btn in more_buttons:
            try:
                btn.click()
                page.wait_for_timeout(150)
            except Exception:
                pass

        # Extract reviews
        containers = page.query_selector_all("div[data-review-id]")

        for container in containers[:max_reviews]:
            # Review text — use SPAN.wiI7pd (actual reviews), not DIV.wiI7pd (owner replies)
            text_el = container.query_selector("span.wiI7pd")
            if not text_el:
                # Fallback
                text_el = container.query_selector("div.MyEned span")
            review_text = text_el.inner_text().strip() if text_el else None

            if not review_text or len(review_text) < 10:
                continue

            # Star rating from aria-label
            rating = None
            stars_el = container.query_selector("span.kvMYJc")
            if stars_el:
                aria = stars_el.get_attribute("aria-label") or ""
                m = re.search(r"(\d)", aria)
                if m:
                    rating = int(m.group(1))

            # Date
            date_el = container.query_selector("span.rsqaWe")
            review_date = date_el.inner_text().strip() if date_el else None

            reviews.append({
                "business_name": business_name,
                "review_text": review_text,
                "rating": rating,
                "review_date": review_date,
                "source": "google",
            })

        browser.close()

    return reviews
