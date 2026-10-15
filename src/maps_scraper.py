"""Google Maps business-listing scraper (public data only).

Searches Google Maps for "<query> in <location>", scrolls the results
feed, opens each place, and extracts the public business details shown
on the listing page: name, address, phone, website, rating, review
count, category and the Maps URL.

Pure helper functions (parse_rating_text, parse_reviews_text, ...) are
kept free of Playwright so they are unit-testable.
"""

from __future__ import annotations

import asyncio
import re
import urllib.parse
from datetime import datetime, timezone

from playwright.async_api import Page

# ---------------------------------------------------------------------------
# Pure, unit-testable parsing helpers
# ---------------------------------------------------------------------------

_RATING_RE = re.compile(r"(\d+(?:[.,]\d+)?)")


def parse_rating_text(aria_label: str | None) -> float | None:
    """'4.6 stars 1,234 reviews' -> 4.6 ; None-safe."""
    if not aria_label:
        return None
    m = _RATING_RE.search(aria_label.replace(",", "."))
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_reviews_text(aria_label: str | None) -> int | None:
    """'4.6 stars 1,234 reviews' -> 1234 ; None-safe."""
    if not aria_label:
        return None
    m = re.search(r"([\d\s,\.]+)\s*reviews?", aria_label, re.IGNORECASE)
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(1))
    return int(digits) if digits else None


def build_search_url(query: str, location: str, language: str = "en") -> str:
    q = urllib.parse.quote_plus(f"{query.strip()} in {location.strip()}")
    return f"https://www.google.com/maps/search/{q}?hl={language}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Playwright interaction helpers
# ---------------------------------------------------------------------------

_CONSENT_BUTTON_TEXTS = (
    "Accept all",
    "I agree",
    "Alle akzeptieren",
    "Aceptar todo",
    "Tout accepter",
)


async def dismiss_consent(page: Page) -> None:
    """Best-effort dismissal of Google's cookie-consent dialog."""
    for text in _CONSENT_BUTTON_TEXTS:
        try:
            btn = page.get_by_role("button", name=text)
            if await btn.count() > 0:
                await btn.first.click(timeout=3000)
                await page.wait_for_timeout(800)
                return
        except Exception:
            continue


async def _scroll_feed(page: Page, target_count: int, max_scrolls: int = 40) -> None:
    """Scroll the results feed until enough cards are loaded or it ends."""
    feed = page.locator('div[role="feed"]')
    try:
        await feed.wait_for(timeout=15000)
    except Exception:
        return
    last_count = 0
    stable = 0
    for _ in range(max_scrolls):
        cards = await page.locator('div[role="feed"] a[href*="/maps/place/"]').count()
        if cards >= target_count:
            break
        if cards == last_count:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        last_count = cards
        try:
            await feed.evaluate("(el) => el.scrollBy(0, el.scrollHeight)")
        except Exception:
            break
        await page.wait_for_timeout(1200)


async def _get_text_safely(locator, timeout: int = 2500) -> str | None:
    try:
        if await locator.count() == 0:
            return None
        txt = await locator.first.inner_text(timeout=timeout)
        return txt.strip() or None
    except Exception:
        return None


async def _get_attr_safely(locator, attr: str, timeout: int = 2500) -> str | None:
    try:
        if await locator.count() == 0:
            return None
        val = await locator.first.get_attribute(attr, timeout=timeout)
        return val.strip() if val else None
    except Exception:
        return None


async def extract_place_detail(page: Page) -> dict:
    """Extract public business details from an open place panel."""
    detail = {
        "name": await _get_text_safely(page.locator("h1")),
        "address": await _get_text_safely(
            page.locator('button[data-item-id="address"]')
        ),
        "phone": None,
        "website": None,
        "rating": None,
        "reviewsCount": None,
        "category": None,
        "googleMapsUrl": page.url.split("?")[0],
    }

    # Phone: data-item-id="phone:tel:+123..."
    phone_href = await _get_attr_safely(
        page.locator('button[data-item-id^="phone:tel:"]'), "data-item-id"
    )
    if phone_href:
        detail["phone"] = phone_href.split("phone:tel:", 1)[-1] or None
    if not detail["phone"]:
        detail["phone"] = await _get_text_safely(
            page.locator('button[data-item-id^="phone:tel:"]')
        )

    # Website: data-item-id="authority"
    detail["website"] = await _get_attr_safely(
        page.locator('a[data-item-id="authority"]'), "href"
    )

    # Rating + reviews: role="img" with "stars ... reviews" aria-label
    rating_label = await _get_attr_safely(
        page.locator('div[role="img"][aria-label*="stars"]'), "aria-label"
    )
    if not rating_label:
        rating_label = await _get_attr_safely(
            page.locator('span[aria-label*="stars"]'), "aria-label"
        )
    detail["rating"] = parse_rating_text(rating_label)
    detail["reviewsCount"] = parse_reviews_text(rating_label)

    # Category: pill-like button under the title block (e.g. "Dentist")
    detail["category"] = await _get_text_safely(
        page.locator("button[jsaction*='category']").first
    )
    if not detail["category"]:
        # Fallback: first button after the h1 title
        detail["category"] = await _get_text_safely(
            page.locator("h1").locator("xpath=following::button[1]")
        )

    detail["scrapedAt"] = now_iso()
    detail["email"] = None  # filled by enrichment step
    return detail


async def scrape_google_maps(
    page: Page,
    query: str,
    location: str,
    max_results: int = 20,
    language: str = "en",
    log=print,
) -> list[dict]:
    """Full scrape flow on an already-created Playwright page."""
    url = build_search_url(query, location, language)
    log(f"Opening {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await dismiss_consent(page)
    await page.wait_for_timeout(2000)

    # If Google shows a single place directly (no feed), handle it.
    feed_present = await page.locator('div[role="feed"]').count() > 0

    leads: list[dict] = []
    seen_urls: set[str] = set()

    async def capture_current_place() -> None:
        try:
            detail = await extract_place_detail(page)
        except Exception as exc:  # never let one bad card kill the run
            log(f"WARN: failed to extract place detail: {exc}")
            return
        key = detail.get("googleMapsUrl") or detail.get("name")
        if key and key not in seen_urls and detail.get("name"):
            seen_urls.add(key)
            leads.append(detail)
            log(f"  + {detail.get('name')}")

    if not feed_present:
        # Direct place page (query matched a single business).
        await page.wait_for_timeout(1500)
        await capture_current_place()
        return leads

    await _scroll_feed(page, max_results)

    cards = page.locator('div[role="feed"] a[href*="/maps/place/"]')
    total = await cards.count()
    log(f"Found {total} result cards, opening up to {max_results}")

    for i in range(min(total, max_results)):
        try:
            await cards.nth(i).click(timeout=8000)
            await page.wait_for_timeout(1800)
            await capture_current_place()
            # Back to the results list.
            try:
                back = page.locator('button[aria-label="Back"]').first
                if await back.count():
                    await back.click(timeout=3000)
                    await page.wait_for_timeout(1000)
            except Exception:
                pass
        except Exception as exc:
            log(f"WARN: card {i} failed: {exc}")
            continue

    return leads
