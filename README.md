# Website Contact Extractor

**Turn any list of business websites into an outreach-ready contact list.** Paste in up to 100 URLs and get back the public contact details each business publishes on its own site: **email addresses, phone numbers, and social media profiles** (Facebook, Instagram, LinkedIn, X, YouTube, TikTok).

Built for agencies, founders, and sales teams doing outbound. Also works great as an **AI-agent tool** (one list in, structured JSON out).

## Input

| Field | Required | Default | Description |
|---|---|---|---|
| `websites` | ✅ | — | Business website URLs (1–100 per run) |
| `includePhones` | — | `true` | Also extract publicly listed phone numbers |
| `includeSocial` | — | `true` | Also extract linked social media profiles |

Example input:

```json
{
  "websites": [
    "https://example-dental-clinic.com",
    "https://example-plumbing.com",
    "https://example-agency.com"
  ],
  "includePhones": true,
  "includeSocial": true
}
```

## Output

One dataset item per website:

```json
{
  "website": "https://example-dental-clinic.com",
  "emails": ["info@example-dental-clinic.com", "appointments@example-dental-clinic.com"],
  "bestEmail": "info@example-dental-clinic.com",
  "phones": ["+966 11 234 5678"],
  "social": {
    "facebook": "https://facebook.com/exampleclinic",
    "instagram": "https://instagram.com/exampleclinic"
  },
  "contactPage": "https://example-dental-clinic.com/contact",
  "status": "ok",
  "contactsFound": 3
}
```

| Status | Meaning |
|---|---|
| `ok` | Site processed (contacts may or may not be found) |
| `no_contacts_found` | Site loaded but published no detectable contacts |
| `invalid_url` | Input could not be parsed as a website URL |
| `fetch_failed` | Site did not respond or blocked the request |

## How it works

1. Fetches each website's homepage (plus `/contact` as a fallback).
2. Extracts `mailto:` / `tel:` links first (highest signal), then scans visible text.
3. Picks the **best email** — preferring the business's own domain, then common roles (`info@`, `contact@`, `sales@`).
4. Collects outbound social profile links, skipping share buttons.
5. Runs up to 5 sites concurrently for speed; typical run of 20 sites finishes in under a minute.

## Pricing

Pay-per-event:

| Event | Price | When it fires |
|---|---|---|
| `run-started` | **$0.50** | Once per run (covers fixed overhead) |
| `contact` | **$0.05** | Per email or phone number extracted |

You only pay for contacts actually found.

## Data & compliance

- **Public business data only.** The Actor reads contact details the business itself publishes on its public pages.
- No login, no form submission, no CAPTCHA bypass, no personal-data harvesting.
- If you use the output for outreach, comply with applicable anti-spam laws (e.g. CAN-SPAM, GDPR) and each recipient's opt-out requests.

## Use cases

- Build cold-email lists from directories or Google results you already have.
- Enrich a CRM with missing emails and phones.
- Find social profiles for multi-channel outreach.
- Feed structured contact JSON into AI sales agents.
