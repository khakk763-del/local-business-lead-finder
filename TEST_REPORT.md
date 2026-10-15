# Test Report — Local Business Lead Finder (Apify Actor)

**Date:** 2026-10-15
**Build:** v0.1, Python 3.12, Apify SDK 4.1.0, Crawlee + Playwright

## What was tested

### ✅ 1. Code compiles (all modules)
`python -m py_compile` on `src/__init__.py`, `src/main.py`, `src/maps_scraper.py`,
`src/enrich.py`, `tests/test_offline.py` — **PASSED**.

### ✅ 2. Offline unit tests (6/6 passed)
`tests/test_offline.py` — no network, no browser:
- `parse_rating_text`: "4.6 stars 1,234 reviews" → 4.6; None-safe; garbage-safe
- `parse_reviews_text`: "4.6 stars 1,234 reviews" → 1234; singular "1 review" → 1
- `build_search_url`: correct Google Maps URL with `hl` language param
- `_clean_candidate`: junk filtering (noreply, example.* domains, image-extension domains)
- `extract_emails_from_html`: mailto: links + plain-text emails extracted, deduped
- `pick_best_email`: prefers same-domain, then role addresses (info@/contact@), then first

### ✅ 3. JSON schemas valid
`INPUT_SCHEMA.json` (required: searchQuery, location) and `.actor/actor.json`
(actorSpecification 1) parse and validate — **PASSED**.

### ✅ 4. SDK API compatibility (verified against installed apify 4.1.0)
- `Actor.charge(event_name, count=1)` — signature confirmed
- `Actor.create_proxy_configuration()` / `ProxyConfiguration.new_url()` — confirmed
- `Actor.push_data`, `Actor.get_input`, `Actor.set_value` — standard, used per docs

### ✅ 5. Email enrichment — live HTTP tests (PASSED)
Against a local fixture server:
- Homepage `mailto:` extraction → `info@alamaldental.sa` ✓
- `/contact` page fallback when homepage has no email → `hello@alamaldental.sa` ✓
Against the real internet (via VM egress proxy):
- Fetched apple.com + httpbin.org successfully; correctly returned `None`
  (neither publishes an extractable contact email) — no-exception path ✓

### ⚠️ 6. Google Maps scraper — live browser test BLOCKED by environment
**Not a code defect.** This VM's egress proxy (`hatch-egress-proxy:3128`)
refuses the Chromium browser's tunneled connections
(`net::ERR_TUNNEL_CONNECTION_FAILED`), even with proxy auth configured.
curl/httpx work through the same proxy; only the browser process is blocked.
The scraper code follows the standard, widely-used Google Maps Playwright
pattern (results feed `div[role="feed"]`, card click → detail panel,
`data-item-id` selectors with per-field try/except fallbacks).

**Required before Store submission:** one live run on the Apify platform
(free $5 monthly credit covers it) with `searchQuery="dentists"`,
`location="Riyadh, Saudi Arabia"`, `maxResults=5`, then inspect the dataset.
If Google shows a consent wall or layout change, selectors in
`src/maps_scraper.py` (`extract_place_detail`) are the single place to fix.

## Pricing implementation (pay-per-event)
- `Actor.charge("run-started")` — fired once per run, first thing in `main()`.
  Configure **$0.50** in Console → Monetization.
- `Actor.charge("lead", count=N)` — fired once with the lead count after
  pushing to the dataset. Configure **$0.02** per event.
- Charge failures are caught and logged (local runs without APIFY_TOKEN
  still execute fully) — production charges work on the platform.

## Not done (needs Khalid)
- `apify push` / Store publication — needs his Apify account + review of this build.
- Monetization request + event price configuration in Console ($0.50 / $0.02).
- KYC + PayPal payout setup (his identity step, per research brief).
- Live 5-lead smoke test on Apify free credits (see §6).

## Files
```
local-business-lead-finder/
├── Dockerfile                  # apify/actor-python-playwright:3.12 base
├── requirements.txt
├── INPUT_SCHEMA.json           # searchQuery, location, maxResults, enrichWebsites, language
├── README.md                   # usage, pricing, examples
├── MONETIZATION.md             # Console pricing setup + margin math
├── TEST_REPORT.md              # this file
├── .actor/actor.json           # Actor metadata + dataset schema
├── src/
│   ├── __init__.py
│   ├── main.py                 # entry: input → charge → scrape → enrich → output
│   ├── maps_scraper.py         # Google Maps Playwright scraper (public data only)
│   └── enrich.py               # public website email enrichment
└── tests/
    └── test_offline.py         # 6/6 passing
```
