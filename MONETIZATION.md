# Monetization setup — Local Business Lead Finder

The Actor fires **pay-per-event** charges in code via `Actor.charge()`; the
USD amounts are configured in the Apify Console (code only names events).

## Events fired by this Actor

| Event name (code) | Configured price | Charged |
|---|---|---|
| `run-started` | **$0.50** | Once per run, always (first thing `main()` does) |
| `lead` | **$0.02** | Once per lead pushed to the dataset (`count` = number of leads) |

## Why the flat `run-started` fee exists

On Apify's free plan the **Actor owner pays the platform compute/proxy
costs of user runs**. A browser launch + proxy session costs roughly
$0.05–$0.15 in platform usage even before any result is produced. Without
a flat fee, a user running the Actor for 2 leads ($0.04 revenue) could
cost the owner more than they earn (documented −1436% margin case).

**Rule: never publish without the `run-started` event priced ≥ $0.30.**
$0.50 gives comfortable headroom on measured costs.

## Console setup steps (owner)

1. Apify Console → Actors → **local-business-lead-finder** → **Monetization** tab.
2. Submit the monetization request if not done (requires Verified Creator = KYC).
3. Add pricing model → **Pay per event**.
4. Add event `run-started` → **$0.50** per event.
5. Add event `lead` → **$0.02** per event.
6. Set a sensible `minimalMaxTotalChargeUsd` (e.g. **$5**) so AI agents and
   cautious users can try it with bounded spend.
7. Save. Prices take effect for new runs (increases need 14 days' notice
   per Store terms; decreases are immediate).

## Cost check before publishing

Run the Actor on the free $5 monthly credit with a 20-lead test and read
the actual platform usage cost in Console → Runs → Usage. Confirm:

    measured cost per run  <  50% of (0.50 + 0.02 × leads)

If not, raise the `run-started` price before publishing.
