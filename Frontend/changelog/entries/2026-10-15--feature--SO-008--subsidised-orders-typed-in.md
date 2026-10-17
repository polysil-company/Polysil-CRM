---
date: 2026-10-15
type: feature
title: "Subsidised orders typed in, with their leads"
dataIds:
  - SO-008
author: Nakul Srivastava
breaking: false
---

## Before

A subsidised order could only be made from a subsidised quotation (PR #142). The backend also takes one typed in, staff only (FS-054, `subsidised-orders-and-small-changes.md`):

- `POST /orders` with `order_type: "subsidised"`, the usual direct-order fields, and `subsidy`;
- `subsidy` holds `lead_ids` (1 to 50, qualified or later, the first being the order's lead), the material, the subsidy and the farmer payable;
- no `lead_id` (`422 lead_from_subsidy`).

The new-order screen offered Commercial and Industrial only. The order's Edit the subsidy changed the amounts but kept the leads as they were. The mock refused a subsidised order typed in.

## Now

- **New order** offers **Subsidised** to staff. A dealer doesn't see it.
- **The Subsidy card** on the new order, once Subsidised is chosen:
  - **Leads:** searched by farmer, mobile or inquiry number among the qualified leads and later, up to 50. They are listed in order, and each can be removed. The first is marked "the order's lead"; the screen says it can't change later. The lead the order started from comes first.
  - the **material** (empty: the order total, shown in the placeholder);
  - the **subsidy**;
  - the **farmer payable** (empty: material less subsidy, worked out as a hint from the priced total).
- **Saving:**
  - it waits for a lead ("Add the farmer's lead for the subsidy.") and asks for the subsidy;
  - the request sends `subsidy` and no `lead_id`;
  - the backend's refusals are said in words: a subsidy or payable above the material, a lead you can't see or that can't take an order (on the Leads field), staff only.
- **Edit the subsidy** on a draft now edits the leads too, with the same picker. The first lead has no Remove: it routes the order (`first_lead_fixed`).
- **Shared code:** the money fields, the draft's checks and the request body move to `order-subsidy-fields.tsx`, used by both screens.
- **The mock:**
  - it makes a subsidised order typed in: the first named lead is its lead, and the leads and amounts are checked as the backend checks them;
  - it refuses `lead_id` beside `subsidy` (`lead_from_subsidy`), and a missing subsidy (`subsidy_missing`);
  - one set of lead and amount checks serves both the create and `PUT /orders/{id}/subsidy`.
- Checked on a desktop in light mode and a phone in dark mode: a new subsidised order from a qualified lead with a second lead added, its card, and Edit the subsidy with the leads. axe found nothing.

## Discussion

- **Not part of go-live** (the user, 13 Oct); plan item 17b.
- **Stacked on #142,** which is stacked on #141 and #140. Merge in that order; retarget each to `integration` first.
- **A lead's name shows in the picker while choosing, not in the edit dialog.** The order's `subsidy.leads` carries the inquiry number only.
- **Not yet checked on staging.**

## Files changed

- `src/features/orders/api/orders.schemas.ts`: `CreateDirectOrder` takes Subsidised and `subsidy`.
- `src/features/orders/components/subsidy-leads-picker.tsx`: new, the leads in order, with search.
- `src/features/orders/components/order-subsidy-fields.tsx`: new, the leads and the three amounts, their checks and the request.
- `src/features/orders/components/order-builder.tsx`: Subsidised for staff, the Subsidy card, the request and its refusals.
- `src/features/orders/components/order-subsidy.tsx`: Edit the subsidy with the leads.
- `src/mocks/handlers/orders.ts`: subsidised orders typed in; the lead and amount checks shared.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/orders/order-subsidy-{new,direct-card,edit-leads}-*`: records and screens.

## Tests

- `src/features/orders/components/order-builder.test.tsx`:
  - names two leads (the first the order's) and the subsidy, then saves a subsidised draft with the material as the total and the payable derived;
  - asks for the subsidy before saving;
  - a dealer isn't offered Subsidised.
- `src/features/orders/components/order-subsidy.test.tsx`:
  - through the API: the lead is the first named; a subsidy above the material, and a lead that can't take an order (named under `subsidy.lead_ids`), are refused;
  - the edit dialog keeps the first lead and adds another.
- Walked through in the mock: desktop light and phone dark.
