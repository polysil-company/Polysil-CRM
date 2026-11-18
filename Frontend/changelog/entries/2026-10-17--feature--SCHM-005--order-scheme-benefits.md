---
date: 2026-10-17
type: feature
title: "Scheme benefits on an order: the preview on a draft, the benefits and To
  pay after submit"
dataIds:
  - SCHM-005
author: Nakul Srivastava
breaking: false
---

## Before

The backend works out scheme benefits on an order (`schemes-contract.md`, FS-031), in two ways:

- `GET /orders/{id}/schemes` previews a draft: the discounts and credits that submit would apply, and what delivery would earn.
- After submit, the order carries `benefits` and `payable`.

The order page showed neither, so a dealer or sales officer couldn't see a scheme discount, and couldn't see that the amount to pay was lower than the invoice.

## Now

- **A Schemes card on the order**, under Items.
- **On a draft:**
  - **Taken off at submit:** each scheme discount (the scheme, the value it was worked on, and the amount off), and each earlier credit it would use.
  - **Earned on delivery:** points, or a credit for the next order, counted on what is dispatched.
  - **The figures:** order total, less scheme benefits, gives "To pay, once submitted".
  - **Kept current:** the card reads the preview again whenever the lines or the total change.
  - **No scheme applies:** a draft through a partner says "No scheme applies to this order as it stands". A direct sale shows no card unless a scheme applies.
- **After submit:**
  - **Applied benefits:** each one, with its scheme. A benefit reversed because the order went back to draft or was cancelled is struck through, with a "Reversed" badge.
  - **To pay:** order total, less scheme benefits. On a subsidised order the starting figure is the farmer's share.
  - **No benefits:** the card is hidden.
- **Scheme names** link to the scheme for those who may view schemes.
- **Errors:**
  - a draft submitted elsewhere (`409 order_not_draft`) re-reads the order;
  - a refused read (403) hides the card;
  - any other error shows with Try again.
- Walked through in the mock as Admin, on a desktop in light mode and a 390 px phone in dark mode: a draft with no scheme, the preview, submit, and the applied benefits. axe found nothing.

## Discussion

- **The invoice never changes.** The card says so, and the order's Totals stay as they are. "To pay" sits in the Schemes card, where the benefits that explain it are.
- **No new client-side rules.** The screen shows what the backend works out. The mock's rules are a sketch and are documented in `src/mocks/data/order-schemes.ts`:
  - only partner orders get benefits;
  - the largest discount that doesn't stack counts, and the stackable ones add to it;
  - credits are used up to what is left to pay.
- **The query key** sits under the order's own key and carries the total and the line count, so a change to the lines reads the preview again.
- **Payments** (`OrderPayments`, item 26) are separate. This only shows `payable`.

## Files changed

- `src/features/orders/api/orders.schemas.ts`: `benefits` on the order, and the preview's contract.
- `src/features/orders/api/orders.api.ts`, `orders.queries.ts`: `getOrderSchemes` and `orderSchemesQueryOptions`.
- `src/features/orders/components/order-schemes.tsx` (new), `order-detail.tsx`: the Schemes card.
- `src/mocks/data/order-schemes.ts` (new), `src/mocks/handlers/orders.ts`, `src/mocks/data/reference.ts`:
  - the preview endpoint;
  - benefits applied at submit;
  - benefits reversed on cancel, return and amend.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SCHM-005.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/schemes/`: records and screens.

## Tests

- `src/features/orders/components/order-schemes.test.tsx`:
  - `[SCHM-005]` through the API:
    - a draft's discount, credit, points and payable;
    - submit stores the benefits and uses the credit;
    - the preview is refused after submit;
    - cancel reverses the benefits and frees the credit.
  - The screen:
    - the preview with To pay;
    - "No scheme applies";
    - a submitted order's benefits, with a reversed one struck through;
    - no card when there are none.
