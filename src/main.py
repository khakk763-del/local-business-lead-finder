"""Local Business Lead Finder — Apify Actor entry point.

Google Maps -> enriched B2B lead lists (public business data only).

Pricing (pay-per-event, configured in Apify Console > Monetization):
    run-started : $0.50 flat per run  (covers fixed browser/proxy overhead —
                                      mandatory margin protection on free plan)
    lead        : $0.02 per lead pushed to the dataset

Code fires the events; the USD amounts live in the Console config.
See MONETIZATION.md for the exact setup steps.
"""

from __future__ import annotations

import asyncio

from apify import Actor
from playwright.async_api import async_playwright

from .enrich import enrich_leads
from .maps_http import fetch_places_http
from .maps_scraper import scrape_google_maps

# Keep runs bounded: never burn more than this many leads per run.
HARD_MAX_RESULTS = 200


async def charge_safely(event_name: str, count: int = 1) -> None:
    """Fire a pay-per-event charge; tolerate local runs without a token."""
    try:
        await Actor.charge(event_name=event_name, count=count)
        Actor.log.info(f"Charged event '{event_name}' x{count}")
    except Exception as exc:  # local dev / no APIFY_TOKEN
        Actor.log.warning(f"Charge '{event_name}' skipped ({exc})")


async def main() -> None:
    async with Actor:
        inp = await Actor.get_input() or {}

        query = (inp.get("searchQuery") or "").strip()
        location = (inp.get("location") or "").strip()
        max_results = int(inp.get("maxResults") or 20)
        enrich_websites = bool(inp.get("enrichWebsites", True))
        language = (inp.get("language") or "en").strip() or "en"

        if not query or not location:
            raise ValueError(
                "Both 'searchQuery' and 'location' are required "
                "(e.g. searchQuery='dentists', location='Riyadh, Saudi Arabia')."
            )
        max_results = max(1, min(max_results, HARD_MAX_RESULTS))

        Actor.log.info(
            f"Lead Finder started: query='{query}' location='{location}' "
            f"max_results={max_results} enrich={enrich_websites}"
        )

        # ---- Flat run-started charge (margin protection) -------------------
        await charge_safely("run-started")

        # ---- Scrape: HTTP-first (no browser), Playwright fallback --------------
        leads: list[dict] = []
        http_ok = False
        try:
            leads = await fetch_places_http(
                query=query,
                location=location,
                max_results=max_results,
                language=language,
                log=Actor.log.info,
            )
            http_ok = len(leads) > 0
            Actor.log.info(f"HTTP scrape yielded {len(leads)} leads")
        except Exception as exc:
            Actor.log.warning(f"HTTP scrape failed, trying browser: {exc}")

        if not http_ok:
            Actor.log.info("Falling back to Playwright browser scrape")
            proxy_config = None
            try:
                proxy_config = await Actor.create_proxy_configuration()
            except Exception as exc:
                Actor.log.warning(f"Proxy configuration unavailable: {exc}")

            async with async_playwright() as pw:
                launch_kwargs: dict = {
                    "headless": True,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ],
                }
                if proxy_config:
                    proxy_url = await proxy_config.new_url()
                    if proxy_url:
                        launch_kwargs["proxy"] = {"server": proxy_url}
                browser = await pw.chromium.launch(**launch_kwargs)
                try:
                    context = await browser.new_context(
                        locale=f"{language}-US",
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0.0.0 Safari/537.36"
                        ),
                    )
                    page = await context.new_page()
                    leads = await scrape_google_maps(
                        page,
                        query=query,
                        location=location,
                        max_results=max_results,
                        language=language,
                        log=Actor.log.info,
                    )
                    await context.close()
                finally:
                    await browser.close()

        Actor.log.info(f"Scraped {len(leads)} raw leads")

        # ---- Enrich ----------------------------------------------------------
        if enrich_websites and leads:
            leads = await enrich_leads(leads)
            Actor.log.info("Website email enrichment done")

        # ---- Output + per-lead charges ---------------------------------------
        charged = 0
        for lead in leads:
            await Actor.push_data(lead)
        if leads:
            await charge_safely("lead", count=len(leads))
            charged = len(leads)

        summary = {
            "searchQuery": query,
            "location": location,
            "leadsFound": len(leads),
            "leadsCharged": charged,
            "eventsFired": ["run-started"] + (["lead x%d" % charged] if charged else []),
        }
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(f"Done: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
