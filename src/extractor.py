"""Website contact extractor — public business contact data only.

Given a business website URL, fetches the homepage (plus /contact as a
fallback) and extracts publicly listed contact details:
email addresses, phone numbers, and social media profile links.

No login, no form submission, no personal-data harvesting:
only contact details the business itself publishes on its public pages.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# International-ish phone pattern: +CC followed by 7-15 digits, allowing
# spaces, dashes, dots, parentheses.
PHONE_RE = re.compile(
    r"(?:\+?\d{1,4}[\s.\-()]*)(?:\d[\s.\-()]*?){7,14}\d"
)

_SOCIAL_DOMAINS = {
    "facebook": ("facebook.com",),
    "instagram": ("instagram.com",),
    "linkedin": ("linkedin.com",),
    "twitter": ("twitter.com", "x.com"),
    "youtube": ("youtube.com",),
    "tiktok": ("tiktok.com",),
}

# Extensions / tokens that are never real contact emails.
_JUNK_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".woff", ".woff2", ".ttf", ".eot", ".ico",
)
_JUNK_LOCALS = {"example", "sample", "test", "noreply", "no-reply", "donotreply"}


def _clean_email(raw: str) -> str | None:
    email = raw.strip().lower().rstrip(".,;:")
    if not EMAIL_RE.fullmatch(email):
        return None
    local, _, domain = email.partition("@")
    if email.endswith(_JUNK_SUFFIXES):
        return None
    if local in _JUNK_LOCALS or "example." in domain:
        return None
    if len(local) < 2:
        return None
    return email


def extract_emails_from_html(html: str) -> list[str]:
    """Extract candidate public contact emails from raw HTML."""
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []

    # 1) mailto: links first — highest signal.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("mailto:"):
            addr = href[7:].split("?")[0]
            cleaned = _clean_email(addr)
            if cleaned and cleaned not in found:
                found.append(cleaned)

    # 2) Plain-text emails in visible text.
    text = soup.get_text(" ", strip=True)
    for m in EMAIL_RE.finditer(text):
        cleaned = _clean_email(m.group(0))
        if cleaned and cleaned not in found:
            found.append(cleaned)

    return found


def _clean_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    # Drop obvious non-phones: too short, too long, all same digit.
    if not 7 <= len(digits) <= 15:
        return None
    if len(set(digits)) < 3:
        return None
    # Drop year-like or version-like numbers.
    if len(digits) <= 8 and digits.startswith(("19", "20")):
        return None
    return raw.strip()


def extract_phones_from_html(html: str) -> list[str]:
    """Extract candidate public phone numbers from raw HTML."""
    soup = BeautifulSoup(html, "lxml")
    found: list[str] = []

    # 1) tel: links first — highest signal.
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().startswith("tel:"):
            cleaned = _clean_phone(href[4:].split("?")[0])
            if cleaned and cleaned not in found:
                found.append(cleaned)

    # 2) Plain-text phone-like sequences.
    text = soup.get_text(" ", strip=True)
    for m in PHONE_RE.finditer(text):
        cleaned = _clean_phone(m.group(0))
        if cleaned and cleaned not in found and len(found) < 10:
            found.append(cleaned)

    return found


def extract_social_from_html(html: str) -> dict[str, str]:
    """Extract social media profile URLs from outbound links."""
    soup = BeautifulSoup(html, "lxml")
    social: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith("http"):
            continue
        try:
            netloc = urlparse(href).netloc.lower()
        except Exception:
            continue
        for name, domains in _SOCIAL_DOMAINS.items():
            if name in social:
                continue
            if any(d in netloc for d in domains):
                # Skip share/intent URLs.
                if any(x in href.lower() for x in ("/share", "/intent/", "sharer.php")):
                    continue
                social[name] = href.split("?")[0]
    return social


def pick_best_email(emails: list[str], website: str) -> str | None:
    """Prefer an address on the business's own domain, else the first."""
    if not emails:
        return None
    try:
        domain = urlparse(website).netloc.lower().lstrip("www.")
    except Exception:
        domain = ""
    for e in emails:
        if domain and e.endswith("@" + domain):
            return e
    for role in ("info@", "contact@", "hello@", "sales@", "support@"):
        for e in emails:
            if e.startswith(role):
                return e
    return emails[0]


def normalize_url(url: str) -> str | None:
    """Ensure a usable http(s) URL; return None if invalid."""
    url = (url or "").strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
        if not parsed.netloc or "." not in parsed.netloc:
            return None
        return url
    except Exception:
        return None


async def extract_contacts(
    client: httpx.AsyncClient, website: str
) -> dict:
    """Fetch a website and extract its public contact details."""
    result: dict = {
        "website": website,
        "emails": [],
        "bestEmail": None,
        "phones": [],
        "social": {},
        "contactPage": None,
        "status": "ok",
        "error": None,
    }

    urls = [website]
    try:
        parsed = urlparse(website)
        if parsed.scheme and parsed.netloc:
            contact_url = urljoin(website, "/contact")
            urls.append(contact_url)
            result["contactPage"] = contact_url
    except Exception:
        pass

    for url in urls[:2]:
        try:
            resp = await client.get(
                url,
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; ContactExtractor/1.0)"},
            )
            if resp.status_code != 200 or "text/html" not in resp.headers.get(
                "content-type", ""
            ):
                continue
            html = resp.text
            for e in extract_emails_from_html(html):
                if e not in result["emails"]:
                    result["emails"].append(e)
            for p in extract_phones_from_html(html):
                if p not in result["phones"]:
                    result["phones"].append(p)
            for name, link in extract_social_from_html(html).items():
                result["social"].setdefault(name, link)
            # Stop early if we already have a solid email + phone.
            if result["emails"] and result["phones"]:
                break
        except Exception as exc:
            result["error"] = str(exc)[:200]
            continue

    result["bestEmail"] = pick_best_email(result["emails"], website)
    if not result["emails"] and not result["phones"] and not result["social"]:
        result["status"] = "no_contacts_found"
    result["contactsFound"] = len(result["emails"]) + len(result["phones"])
    return result


async def extract_batch(
    websites: list[str], max_concurrency: int = 5, log=print
) -> list[dict]:
    """Extract public contacts for a batch of websites concurrently."""
    import asyncio

    sem = asyncio.Semaphore(max_concurrency)

    async with httpx.AsyncClient() as client:
        async def _one(url: str) -> dict:
            normalized = normalize_url(url)
            if not normalized:
                return {
                    "website": url,
                    "emails": [],
                    "bestEmail": None,
                    "phones": [],
                    "social": {},
                    "contactPage": None,
                    "status": "invalid_url",
                    "error": "Could not parse as a website URL",
                    "contactsFound": 0,
                }
            async with sem:
                try:
                    res = await extract_contacts(client, normalized)
                    log(f"  {'✓' if res['contactsFound'] else '·'} {normalized} "
                        f"({res['contactsFound']} contacts)")
                    return res
                except Exception as exc:
                    return {
                        "website": normalized,
                        "emails": [],
                        "bestEmail": None,
                        "phones": [],
                        "social": {},
                        "contactPage": None,
                        "status": "fetch_failed",
                        "error": str(exc)[:200],
                        "contactsFound": 0,
                    }

        # Preserve input order in results.
        return [await _one(u) for u in websites]
