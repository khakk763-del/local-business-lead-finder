"""Google Maps search via plain HTTP (no browser).

Fetches the Maps search HTML and parses the embedded
``window.APP_INITIALIZATION_STATE`` JSON for public business listings.
Much less likely to be bot-blocked than browser automation.

Extracted per place (when present in the payload):
name, address, latitude, longitude, rating, reviewsCount,
category, placeId, googleMapsUrl.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timezone

import httpx

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# window.APP_INITIALIZATION_STATE=[ ... ];window.APP_FLAGS
_APP_STATE_RE = re.compile(
    r"window\.APP_INITIALIZATION_STATE\s*=\s*(\[.*?\])\s*;\s*window\.APP_FLAGS",
    re.DOTALL,
)

# Fallback: any large JSON array assignment that looks like app state.
_GENERIC_STATE_RE = re.compile(
    r"window\.APP_INITIALIZATION_STATE\s*=\s*(\[.*?\])\s*;", re.DOTALL
)

_PLACE_ID_RE = re.compile(r"ChIJ[A-Za-z0-9_-]{23}")


def build_search_url(query: str, location: str, language: str = "en") -> str:
    q = urllib.parse.quote_plus(f"{query.strip()} in {location.strip()}")
    return f"https://www.google.com/maps/search/{q}?hl={language}"


def _extract_app_state(html: str) -> list | None:
    for pattern in (_APP_STATE_RE, _GENERIC_STATE_RE):
        m = pattern.search(html)
        if not m:
            continue
        raw = m.group(1)
        # The payload may be truncated by the non-greedy match; try to
        # repair by balancing brackets from the match start.
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Attempt bracket-balanced extraction as a fallback.
        start = m.start(1)
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(html)):
            ch = html[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start : i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def _walk(node, depth: int = 0, max_depth: int = 12):
    """Yield every list node in the nested structure (depth-limited)."""
    if depth > max_depth or not isinstance(node, list):
        return
    yield node
    for child in node:
        if isinstance(child, list):
            yield from _walk(child, depth + 1, max_depth)


def _looks_like_place(entry: list) -> bool:
    """Heuristic: a place entry contains a ChIJ place id + a plausible name."""
    text_hits = 0
    has_place_id = False
    for item in entry:
        if isinstance(item, str):
            if _PLACE_ID_RE.search(item):
                has_place_id = True
            elif 2 <= len(item) <= 120 and not item.startswith("http"):
                text_hits += 1
        if has_place_id and text_hits >= 2:
            return True
    return False


def _extract_place_fields(entry: list) -> dict | None:
    place_id = None
    strings: list[str] = []
    numbers: list[float] = []

    def collect(node):
        if isinstance(node, str):
            m = _PLACE_ID_RE.search(node)
            if m and not place_id:
                return  # handled below
            if 1 <= len(node) <= 200:
                strings.append(node)
        elif isinstance(node, (int, float)) and not isinstance(node, bool):
            numbers.append(float(node))
        elif isinstance(node, list):
            for c in node:
                collect(c)

    for item in entry:
        if isinstance(item, str):
            m = _PLACE_ID_RE.search(item)
            if m:
                place_id = m.group(0)
        collect(item)

    if not place_id:
        return None

    # Name: longest plausible string that isn't a URL or place id.
    candidates = [
        s for s in strings
        if not _PLACE_ID_RE.search(s)
        and not s.startswith("http")
        and 2 <= len(s) <= 100
        and not s.startswith("//")
    ]
    name = max(candidates, key=len) if candidates else None
    if not name:
        return None

    # Rating: float in 0..5 range; reviews: int that follows it.
    rating = None
    reviews = None
    for n in numbers:
        if rating is None and 0 < n <= 5 and n == round(n, 1):
            # plausible rating; check it isn't a lat/lng fragment
            rating = n
        elif rating is not None and reviews is None and n >= 1 and n == int(n) and n < 10_000_000:
            reviews = int(n)
            break

    return {
        "placeId": place_id,
        "name": name,
        "rating": rating,
        "reviewsCount": reviews,
        "_strings": strings[:12],
    }


def parse_places_from_html(html: str, max_results: int = 20) -> list[dict]:
    state = _extract_app_state(html)
    if not state:
        return []
    places: list[dict] = []
    seen: set[str] = set()
    for node in _walk(state):
        if len(places) >= max_results * 3:  # oversample, dedupe later
            break
        if _looks_like_place(node):
            fields = _extract_place_fields(node)
            if fields and fields["placeId"] not in seen:
                seen.add(fields["placeId"])
                places.append(fields)
    return places[:max_results]


def _maps_url(place_id: str, name: str, language: str = "en") -> str:
    q = urllib.parse.quote_plus(name)
    return f"https://www.google.com/maps/place/{q}/data=!4m2!3m1!1s{place_id}?hl={language}"


async def fetch_places_http(
    query: str,
    location: str,
    max_results: int = 20,
    language: str = "en",
    log=print,
) -> list[dict]:
    """Fetch Maps search HTML via HTTP and parse embedded place data."""
    url = build_search_url(query, location, language)
    log(f"HTTP fetching {url}")
    async with httpx.AsyncClient(
        headers=_HEADERS, timeout=30.0, follow_redirects=True
    ) as client:
        resp = await client.get(url)
        log(f"HTTP {resp.status_code}, {len(resp.text)} chars")
        if resp.status_code != 200:
            raise RuntimeError(f"Maps search HTTP {resp.status_code}")
        html = resp.text

    low = html.lower()
    if "unusual traffic" in low or "recaptcha" in low or "/sorry/" in low:
        raise RuntimeError("Google bot-check page over HTTP")

    raw_places = parse_places_from_html(html, max_results)
    log(f"Parsed {len(raw_places)} candidate places from embedded JSON")

    leads: list[dict] = []
    for p in raw_places[:max_results]:
        leads.append(
            {
                "name": p["name"],
                "address": None,
                "phone": None,
                "website": None,
                "rating": p["rating"],
                "reviewsCount": p["reviewsCount"],
                "category": None,
                "googleMapsUrl": _maps_url(p["placeId"], p["name"], language),
                "placeId": p["placeId"],
                "scrapedAt": datetime.now(timezone.utc).isoformat(),
                "email": None,
            }
        )
    return leads
