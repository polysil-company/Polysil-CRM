---
date: 2026-10-15
type: feature
title: "Subsidised quotations: the subsidy step and card"
dataIds:
  - QUOT-014
author: Nakul Srivastava
breaking: false
---

## Before

The backend takes `sales_type: "subsidised"` on a quotation (FS-057, `subsidised-quotations.md`). The quotation carries the subsidy calculator's answer for one farmer category, through:

- `PUT /quotations/{id}/subsidy`, a draft only;
- `GET /quotations/{id}/subsidy/calculation`, the full answer stored with it.

Sending needs the subsidy (`422 subsidy_missing`).

The frontend offered only Commercial and Industrial, and said subsidised quotations waited on the client's rules.

## Now

- **The builder** offers **Subsidised** for a subsidised lead, or a quotation that already is one, and starts there for a subsidised lead. It says: "Save the draft, then calculate its subsidy on the quotation."
- **The quotation's Subsidy card**, on a subsidised quotation:
  - a draft without one says so, with **Calculate the subsidy**;
  - once saved, it shows the scheme, system and masters' date; the category; what the scheme pays; what the farmer pays; the total cost (with CG's inspection outside the cap, and AP's GST paid by the state where they apply);
  - **Recalculate** on a draft, and **Show the full calculation** (the stored answer, as on an application);
  - `calculation_total_differs` reads "The calculation's total differs from the quotation's lines. Recalculate if the lines changed." It is no longer repeated in the general warnings.
- **The subsidy step** (`/quotations/{id}/subsidy`, a draft only):
  - the calculator for the lead's scheme (`GET /subsidy-schemes/for-lead`) and irrigation system, with the scheme's own inputs;
  - then the farmer's category, only one that applies on every crop block, with the subsidy and the farmer's share beside each;
  - saving sends the calculation without the scheme, as the backend asks, and returns to the quotation;
  - it says why it can't run: not subsidised, not a draft, the lead hidden, the lead's state without a scheme, or the system without a calculation.
- **Refusals:**
  - sending without a subsidy: "Calculate the subsidy first";
  - the lead's scheme or system changed: calculate again;
  - on save: `not_subsidised`, `quotation_not_draft` and `masters_not_in_force` in words, and field refusals listed.
- **Shared code:** "applies on every crop block" moved into the calculator's library, shared with starting an application.
- **The mock:**
  - it accepts subsidised drafts;
  - it calculates and stores the subsidy on the lead's scheme;
  - it compares the calculation's total with the lines (1 %);
  - it serves the stored calculation, and refuses to send a subsidised draft without its subsidy.
- Checked on a desktop in light mode and a phone in dark mode: from a subsidised lead to a draft, the step, and the saved subsidy. axe found nothing.

## Discussion

- **Not part of go-live** (the user, 13 Oct); built in the plan's order.
- **Stacked on #140,** whose calculator takes each scheme's inputs (AP, CG, RJ, UP). Merge #140 first, then retarget this to `integration`.
- **Making an order from an accepted subsidised quotation** is plan item 17.
- **Recalculating starts the calculator empty.** The stored calculation is the answer, not the request that produced it, so the inputs can't be refilled from it.
- **Not yet checked on staging.**

## Files changed

- `src/features/quotations/api/quotations.schemas.ts`, `quotations.api.ts`, `quotations.queries.ts`, `quotations.mutations.ts`: the subsidy block, Subsidised as priced, `setQuotationSubsidy`, `getQuotationSubsidyCalculation`.
- `src/features/quotations/components/quotation-subsidy.tsx`: new, the card and the step.
- `src/app/(app)/(sales)/quotations/[quotationId]/subsidy/page.tsx`: new, the route.
- `src/features/quotations/components/quotation-detail.tsx`: the card, and the warning it says.
- `src/features/quotations/components/quotation-builder.tsx`: Subsidised for a subsidised lead.
- `src/features/quotations/lib/quotation-lifecycle.ts`: the send refusals.
- `src/features/subsidy/lib/calculator-draft.ts`, `src/features/subsidy/components/start-application.tsx`: `applicableEverywhere` shared.
- `src/mocks/handlers/quotations.ts`, `src/mocks/db.ts`, `src/mocks/handlers/subsidy-applications.ts`: the subsidy routes, the send check, and `schemeForLead` exported.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: QUOT-014.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/quotations/quote-subsidy-*`: records and screens.

## Tests

- `src/features/quotations/components/quotation-subsidy.test.tsx`:
  - a subsidised draft isn't sent without its subsidy;
  - one category's figures stored, and the full calculation with them;
  - a category that doesn't apply, and a quotation that isn't subsidised, refused;
  - the card: none yet with its link; then the scheme, the farmer, Recalculate, the total differing, and the full calculation;
  - the step: calculated on the lead's scheme and system, a category chosen and saved;
  - a sent quotation's subsidy can't change.
- Walked through in the mock: desktop light and phone dark.
