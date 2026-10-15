# Local Business Lead Finder

**Google Maps → enriched B2B lead lists.** Search any business category in any location and get outreach-ready leads: business name, address, phone, website, Google rating, review count, category, Maps URL — plus the **public contact email** found on each business's website.

Built for agencies, founders, and sales teams doing outbound. Also works great as an **AI-agent tool** (one query in, structured JSON out).

## Input

| Field | Required | Default | Description |
|---|---|---|---|
| `searchQuery` | ✅ | — | Business category, e.g. `dentists`, `plumbers`, `marketing agencies` |
| `location` | ✅ | — | Where to search, e.g. `Riyadh, Saudi Arabia` |
| `maxResults` | — | `20` | Max leads to return (1–200) |
| `enrichWebsites` | — | `true` | Visit each website to find its public contact email |
| `language` | — | `en` | Results language code (`en`, `ar`, `es`, …) |

Example input:

```json
{
  "searchQuery": "dentists",
  "location": "Riyadh, Saudi Arabia",
  "maxResults": 20,
  "enrichWebsites": true,
  "language": "en"
}
```

## Output

Each lead is pushed to the default dataset:

```json
{
  "name": "Al Amal Dental Clinic",
  "address": "King Fahd Rd, Al Olaya, Riyadh",
  "phone": "+966112345678",
  "website": "https://alamaldental.sa",
  "email": "info@alamaldental.sa",
  "rating": 4.6,
  "reviewsCount": 231,
  "category": "Dentist",
  "googleMapsUrl": "https://www.google.com/maps/place/...",
  "scrapedAt": "2026-10-15T17:00:00+00:00"
}
```

## Pricing (pay-per-event)

| Event | Price | What it covers |
|---|---|---|
| `run-started` | **$0.50** flat | One charge per run — covers browser launch & fixed overhead |
| `lead` | **$0.02** per lead | Charged once per lead pushed to the dataset |

Example: 20 leads = $0.50 + 20 × $0.02 = **$0.90**. You always see the max cost before running.

## Data & compliance

- **Public business listings only.** The Actor reads what Google Maps publicly displays.
- Emails come only from businesses' own public websites (contact pages).
- No logins, no CAPTCHA bypassing, no personal-data harvesting.
- Respects `robots.txt` on enriched websites.

## Local development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
APIFY_LOCAL_STORAGE_DIR=./storage .venv/bin/python -m src.main
# put test input in storage/key_value_stores/default/INPUT.json
```

## Pricing setup (for the owner)

Event prices are configured in **Apify Console → Actor → Monetization** (not in code). Steps in `MONETIZATION.md`.
