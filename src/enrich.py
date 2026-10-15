"""Website email enrichment — public business contact emails only.

Given a business website URL, fetch the homepage (and /contact as a
fallback) and extract publicly listed contact email addresses.
No login, no form submission, no personal-data harvesting:
only emails the business itself publishes on its public pages.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Extensions / tokens that are never real contact emails.
_JUNK_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js",
    ".woff", ".woff2", ".ttf", ".eot", ".ico",
)
_JUNK_LOCALS = {"example", "sample", "test", "noreply", "no-reply", "donotreply"}


def _clean_candidate(raw: str) -> str | None:
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
            cleaned = _clean_candidate(addr)
            if cleaned and cleaned not in found:
                found.append(cleaned)

    # 2) Plain-text emails in visible text.
    text = soup.get_text(" ", strip=True)
    for m in EMAIL_RE.finditer(text):
        cleaned = _clean_candidate(m.group(0))
        if cleaned and cleaned not in found:
            found.append(cleaned)

    return found


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
    # Prefer common contact roles over personal-looking addresses.
    for role in ("info@", "contact@", "hello@", "sales@", "support@"):
        for e in emails:
            if e.startswith(role):
                return e
    return emails[0]


async def enrich_website_email(
    client: httpx.AsyncClient, website: str
) -> str | None:
    """Fetch a business website and return its best public contact email."""
    urls = [website]
    try:
        parsed = urlparse(website)
        if parsed.scheme and parsed.netloc:
            urls.append(urljoin(website, "/contact"))
    except Exception:
        pass

    for url in urls[:2]:
        try:
            resp = await client.get(
                url,
                timeout=12.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; LeadFinder/1.0)"},
            )
            if resp.status_code != 200 or "text/html" not in resp.headers.get(
                "content-type", ""
            ):
                continue
            emails = extract_emails_from_html(resp.text)
            best = pick_best_email(emails, website)
            if best:
                return best
        except Exception:
            continue
    return None


async def enrich_leads(leads: list[dict], max_concurrency: int = 5) -> list[dict]:
    """Add a public `email` field to leads that have a website."""
    import asyncio

    sem = asyncio.Semaphore(max_concurrency)

    async with httpx.AsyncClient() as client:
        async def _one(lead: dict) -> dict:
            if not lead.get("website"):
                return lead
            async with sem:
                try:
                    lead["email"] = await enrich_website_email(client, lead["website"])
                except Exception:
                    lead["email"] = None
            return lead

        return [await _one(lead) for lead in leads]
