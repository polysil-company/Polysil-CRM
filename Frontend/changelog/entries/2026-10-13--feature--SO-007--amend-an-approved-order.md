---
date: 2026-10-13
type: feature
title: Amend an approved order
dataIds:
  - SO-007
author: Nakul Srivastava
breaking: false
---

## Before

Once an order was approved, nothing on it could change. The only way out was to cancel it and type a new one, which lost its number and its history. The backend has served `POST /orders/{id}/amend` since FS-036 (`settings-amend-reopen-contract.md`, migration 041), with "Amend after a voided dispatch" added in migration 064. The frontend had no screen for it.

## Now

- **Amend order…** sits in an approved order's More menu, next to Cancel.
  - **Who sees it:** staff who edit orders, or who own the order.
  - **When:** while nothing has shipped.
  - **Never offered:** to partner users, on a replacement order, or once something has shipped.
- **The dialog.** It asks what needs to change, and why. The reason is required, and is kept on the order and its history. It explains what follows:
  - the order goes back to draft under the same number;
  - it needs approval again;
  - its PDF is withdrawn until then;
  - any payment instalments are cleared for Accounts to set again.
- **The amended draft** shows a banner: "Amended after approval · it was approved at ₹…".
  - It counts the amends when there were several.
  - It shows the reason, for staff; a partner user reads none.
  - It says what to do next; while the order waits again, it says that too.
- **The old approval chain** stays visible as "Approval before the amend", saying it starts again from the first step on submit.
- **The history** reads "Amended: back to draft" with the approved total. The lead's history reads "Sales order amended, back to draft".
- **The edit screen** fixes the order type of an amended order, and says why. A refused change (`422 order_type_fixed`) has its own sentence.
- **Refusals, each in words:**
  - `409 voided_dispatch_holds_lines`: "This order had a dispatch voided. Cancel it and create a new one.", as the backend's handover asks;
  - `409 order_has_payments`;
  - `422 order_type_fixed`;
  - `409 order_dispatched`;
  - `409 status_changed`, which closes the dialog and shows the latest.
- Checked on a desktop in light mode and a phone in dark mode. axe found nothing on the dialog, the amended order or the edit screen.

## Discussion

- **In the More menu, beside Cancel,** as the contract's "Screens" section puts it. It is rare, and it undoes an approval, so it doesn't sit with the everyday buttons.
- **What the screen checks first:** staff only (the backend refuses portal roles, GAP-352), the order approved, nothing shipped, not a replacement.
- **What only the backend knows:** whether money is allocated, or a voided dispatch still names the lines. The order carries neither, so the backend's refusal says it in words.
- **The old chain on a draft.** `GET /orders/{id}` returns the order's latest approval request. After an amend that is the chain that approved it before, so a draft showed four green steps. Retitling it keeps the record without suggesting the draft is approved.
- **The setting `order_amend_reapproval`** (`always` or `value_rises`) decides whether a total that didn't rise goes straight to Accounts on resubmit. The screen doesn't read it. The wording says "needs approval again", which holds either way. The settings screen is plan item 21.
- **Plan records:** `Docs/Plan.md` had two copies of the §9 paragraph after #114. They are merged into one, so partners and documents both appear once.

## Files changed

- `src/features/orders/api/orders.schemas.ts`: `amend_count`, `amended_from_total`, `amend_reason` on the order (defaulted, so older responses still parse).
- `src/features/orders/api/orders.api.ts`, `orders.mutations.ts`: `amendOrder`, `useAmendOrder`.
- `src/features/orders/lib/order-lifecycle.ts`: the `amend` action, `isStaff` in the permissions, four refusals, the `order.amended` history line.
- `src/features/orders/hooks/use-order-actions.ts`: passes `isStaff`.
- `src/features/orders/components/order-actions.tsx`, `order-action-dialog.tsx`: the menu item and the dialog.
- `src/features/orders/components/order-detail.tsx`: the amended banner.
- `src/features/orders/components/order-approval.tsx`: "Approval before the amend".
- `src/features/orders/components/order-builder.tsx`: the order type fixed after an amend; `order_type_fixed`.
- `src/features/leads/lib/timeline-entries.ts`: the lead's history line.
- `src/mocks/handlers/orders.ts`: `POST /orders/:id/amend` with the backend's rules, in its order.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SO-007.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/orders/`: records and screens.

## Tests

- `src/features/orders/lib/order-lifecycle.test.ts`, `[SO-007] Amend an approved order`:
  - who is offered it, and who isn't (partner, Dispatch, shipped, replacement, not approved);
  - the refusals in words;
  - the history line.
- `src/features/orders/api/orders.test.ts`, `[SO-007] amendOrder`:
  - back to draft under its number, with the approved total, the reason and the history event;
  - 409 `order_dispatched`, 409 `status_changed`, 403 for a dealer.
- `src/features/orders/components/orders-ui.test.tsx`, `[SO-007] Amend an approved order`:
  - the whole flow, with the empty reason refused, the banner and the retitled chain;
  - the voided-dispatch refusal in the dialog;
  - nothing offered to a dealer.
- Walked through in the mock as admin: desktop light (menu, dialog with the empty reason, the amended draft, the edit screen) and phone dark (dialog, amended draft).
