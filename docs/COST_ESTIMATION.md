# Repair-plan budget builder

Open a completed assessment and choose **Cost estimate**.

1. Review suggested work items. A single visit/project is an explicit assumption, not a quantity extracted from the inspection.
2. Add the work you intend to commission for each task. Choose a compatible published reference, or enter a custom quote/planning allowance with its source.
3. Enter quantity and whether it is assumed, measured or quoted. Whole counts are required for visits, outlets and projects; square footage can be fractional.
4. Set a location label, your local price factor, contingency and a separate allowance for fees, permits or tax. Location text does not call a geocoder or automatically calibrate prices.
5. Mark a task covered only if the selected rows include all the work for that planned task. Covering diagnostic/evaluation tasks does not cover the corrective repairs they may discover. Materials-only rows cannot cover a complete task.
6. Save before changing tabs. Export the saved budget or the complete assessment.

## Calculation

For each complete active row:

`line low/high = quantity × source unit low/high`

`adjusted subtotal = sum(line amounts) × user local factor`

`contingency = adjusted subtotal × contingency percentage`

`budget range = adjusted subtotal + contingency + separate allowance`

Currency is rounded with Decimal and half-up cents. The planning midpoint is the arithmetic average of the resulting bounds; it is not a statistical prediction. Contingency defaults to 15% as an editable scenario, not a researched recommendation.

No automatic tax, contractor markup, diagnostic visit fee or bundling discount is added. A service call may be credited toward installed work; selecting both an electrician visit and installed GFCI work produces an overlap warning. Custom quotes are also scaled by the user's local factor, with a warning when the factor differs from 1.00.

Missing quantities, incomplete custom ranges and obsolete plan tasks are excluded, not treated as free repairs. The total remains visibly partial until the user marks the current planned scopes covered with complete work items. Unknown future repairs, concealed damage and excluded work still remain outside the estimate.

## Published references

Snapshot checked October 30, 2026. These are small curated reference facts, not a licensed real-time contractor-pricing database. Prices depend on local scope and conditions.

| Work | Unit range | Source | Source date |
|---|---|---|---|
| Electrician service call / first hour | $100–$200 per visit | [Angi](https://www.angi.com/articles/how-much-does-it-cost-hire-electrician.htm) | 2026-10-21 |
| Existing outlet GFCI replacement | $100–$200 per outlet | [Angi](https://www.angi.com/articles/how-much-should-it-cost-electrician-replace-combination-gfci-switch-and-receptacle.htm) | 2026-09-23 |
| Gutter cleaning | $100–$250 per typical project | [HomeGuide](https://homeguide.com/costs/gutter-cleaning-cost) | 2025-11-07 |
| Roof cleaning | $250–$600 per typical project | [HomeGuide](https://homeguide.com/costs/gutter-cleaning-cost) | 2025-11-07 |
| Basic above-ground downspout extension | $5–$20 each, materials only | [HomeGuide](https://homeguide.com/costs/downspouts-cost) | 2025-11-07 |
| Buried downspout drainage extension | $150–$350 per typical installation | [HomeGuide](https://homeguide.com/costs/downspouts-cost) | 2025-11-07 |
| Standard outdoor handrail installation | $275–$1,150 per typical project | [Angi](https://www.angi.com/articles/price-install-outdoor-handrail-sidewalk-two-steps.htm) | 2026-09-23 |
| Basic crawlspace encapsulation | $2–$4 per square foot | [Angi](https://www.angi.com/articles/how-much-does-crawl-space-encapsulation-cost.htm) | 2026-10-28 |

Each catalog item records inclusions and exclusions. Encapsulation pricing is not vapor-barrier material-only pricing and is not an automatic recommendation for a moisture finding. A specialist must confirm that work is appropriate. No unsupported catalog rate is supplied for unidentified moisture remediation, structural repairs or an undefined specialist scope; those require a custom rate/quote.

## Persistence and consistency

`budget_versions` stores append-only draft revisions and computed snapshots, including the rate catalog version and source data. A stale expected revision is rejected with 409. The current view is recomputed against the current plan, so costs from removed/rejected scopes disappear from totals while saved old rows remain inspectable as obsolete items. Historical rate/output snapshots are available at the budget history endpoint and do not change when the catalog changes.

Endpoints:

- `GET /api/reports/{id}/budget`
- `POST /api/reports/{id}/budget/preview` — calculates without saving
- `PUT /api/reports/{id}/budget` — validates and appends a revision
- `GET /api/reports/{id}/budget/history`
- `GET /api/reports/{id}/budget/export`

This module is deterministic local Python. No model call, external price API or additional inference cost occurs during estimation.
