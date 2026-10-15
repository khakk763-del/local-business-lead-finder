"""Website Contact Extractor — Apify Actor entry point.

Give it a list of business websites; get back the public contact details
each business publishes: email addresses, phone numbers, and social
media profiles. Ideal for building outreach lists.

Pricing (pay-per-event, configured in Apify Console > Monetization):
    run-started : $0.50 flat per run  (covers fixed overhead —
                                      mandatory margin protection)
    contact     : $0.05 per contact extracted (each email or phone)

Code fires the events; the USD amounts live in the Console config.
"""

from __future__ import annotations

import asyncio

from apify import Actor

from .extractor import extract_batch

# Keep runs bounded: never process more than this many sites per run.
HARD_MAX_SITES = 100


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

        websites = inp.get("websites") or []
        if isinstance(websites, str):
            websites = [websites]
        websites = [w for w in websites if isinstance(w, str) and w.strip()]
        include_phones = bool(inp.get("includePhones", True))
        include_social = bool(inp.get("includeSocial", True))

        if not websites:
            raise ValueError(
                "'websites' is required: a list of 1-100 business website URLs."
            )
        websites = websites[:HARD_MAX_SITES]

        Actor.log.info(
            f"Contact Extractor started: {len(websites)} websites, "
            f"phones={include_phones} social={include_social}"
        )

        # ---- Flat run-started charge (margin protection) -------------------
        await charge_safely("run-started")

        # ---- Extract --------------------------------------------------------
        results = await extract_batch(
            websites, max_concurrency=5, log=Actor.log.info
        )

        # Respect the include toggles in the output.
        for r in results:
            if not include_phones:
                r["phones"] = []
            if not include_social:
                r["social"] = {}
            r["contactsFound"] = len(r["emails"]) + len(r["phones"])

        # ---- Output + per-contact charges ------------------------------------
        total_contacts = 0
        ok_count = 0
        for r in results:
            await Actor.push_data(r)
            total_contacts += r["contactsFound"]
            if r["status"] in ("ok", "no_contacts_found"):
                ok_count += 1

        if total_contacts:
            await charge_safely("contact", count=total_contacts)

        summary = {
            "websitesProcessed": len(results),
            "websitesOk": ok_count,
            "contactsFound": total_contacts,
            "contactsCharged": total_contacts,
            "eventsFired": ["run-started"]
            + (["contact x%d" % total_contacts] if total_contacts else []),
        }
        await Actor.set_value("OUTPUT", summary)
        Actor.log.info(f"Done: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
