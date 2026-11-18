---
date: 2026-10-18
type: feature
title: A consolidated order from several quotations of one dealer
dataIds:
  - SO-011
author: Nakul Srivastava
breaking: false
---

## Before

**Place order** made a draft from one accepted quotation. The backend already took several (`POST /orders` with several `quotation_ids`), but nothing on screen sent more than one. A dealer with several farmers' quotations needed several orders.

## Now

Built to `orders-api-contract.md` §3 ("From quotations") and the generated `orders.md`.

**In Place order** (on a dealer's accepted, current quotation)

- A section lists the dealer's other accepted, current quotations (`GET /quotations?status=accepted&partner_id=`). Each shows its number, total, party and lead, with a box to tick.
- As they are ticked, it shows how many quotations and their total together. When they span several leads, it says the order is consolidated: the dealer is the party and it has no single lead.
- **Make draft order** sends this quotation and those ticked. The dialog's description counts them too.
- **Not offered** on a direct quotation (no dealer) or a subsidised one, which is ordered alone. An export quotation offers only exports, and a domestic one never offers an export.
- Loading, an empty list ("No other accepted quotation of this dealer is waiting"), and an error that still lets this quotation be ordered alone.

**Refusals**

- `409 quotation_on_order` naming a ticked quotation unticks it and marks it "already on an order". It says so and lets the user carry on without it.
- `422 quotations_disagree` now says which field differs (the place of supply, the price date, the seller registration…). An unknown field reads from its key.

**Mock**

- The quotation list takes `partner_id`.
- One dealer starts with a second accepted quotation, on another lead, to the same place, so the consolidated order can be tried.

**Backend ask**

- **BE-029:** an `orderable` filter on `GET /quotations`. The list can't tell which quotations are already on an order, so one can show as a choice until `POST /orders` refuses it.

Walked as Admin on a desktop in light mode and a touch phone in dark mode:

- the dealer's other quotations;
- one already on an order, refused, unticked and marked;
- two ticked;
- the new draft "For Babra Farm Supplies".

Axe found nothing, with no sideways scroll. The only console error is the deliberate 409.

## Discussion

- **The walk found the case BE-029 asks about.** The seeded dealer's QT/…/00002 is on an order, yet listed. The first message, "Open that order instead", didn't fit an added quotation, so the refusal now says it was unticked.
- **"Deliver to" starts from this quotation's party.** For a consolidated order the dealer's address may be the right one. The user changes it, as before.
- **The backend decides what may join.** The list shows the dealer's quotations; agreement on place, seller, price date, office and territory is checked by `POST /orders`, which names the field.
- **This is item 37.** Item 38 (the dealer portal walk) follows.

## Files changed

- `src/features/orders/components/consolidate-quotations.tsx`: new, the dealer's other quotations to tick.
- `src/features/orders/components/place-order.tsx`: the section, the ids sent, a quotation on an order unticked and marked.
- `src/features/orders/lib/order-lifecycle.ts`: `quotations_disagree` names the field.
- `src/features/quotations/api/quotations.schemas.ts`, `.api.ts`: an optional `partnerId` on the list.
- Mock: `src/mocks/handlers/quotations.ts` (`partner_id`), `src/mocks/db.ts` (a dealer with two waiting quotations).
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SO-011.
- `docs/Backend-Tasks.md`: BE-029.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/orders/consolidate*`.

## Tests

`src/features/orders/components/consolidate.test.tsx`, 4 tests in `[SO-011] A consolidated order from several quotations of one dealer`:

- the dealer's other quotation ticked, the consolidated note, and one order of both;
- a quotation on an order already, unticked and marked, with the message;
- the place of supply named when the quotations don't match;
- nothing to add on a direct quotation.

The other 98 order tests still pass.

To check by hand in the mock, as Admin:

1. Open quotation QT/GJ/2026-27/00025 and select **Place order**.
2. Tick QT/GJ/2026-27/00028 and select **Make draft order**.
3. Try QT/GJ/2026-27/00002 too, which is already on an order.
