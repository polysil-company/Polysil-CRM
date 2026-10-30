---
date: 2026-10-04
type: feature
title: "Dispatch queue: orders to ship and the dispatch log"
dataIds:
  - DISP-001
  - DISP-002
  - ACCT-001
author: Nakul Srivastava
breaking: false
---

## Before

"Dispatch queue" and "Accounts queue" were "Soon" items in the sidebar. Dispatch could record a dispatch only by finding an approved order in the Sales orders list and opening it. Nothing showed what had left across all orders, though the backend serves `GET /dispatches`.

## Now

**Dispatch queue** (`/dispatch`), for anyone with the `dispatch` module.

**To ship** lists every approved order still waiting to leave:

- each order's number and status, the party, the order type, the total, and when it was submitted;
- how much has gone, as a bar with "46% sent";
- a count at the top: "2 orders still to ship".

**Record a dispatch** opens the order with the record form already open, using `?record=dispatch`:

- Someone who may only look sees no button.
- The link does nothing for them, or on an order that can't ship.

**Dispatched** is the log of what left, newest first:

- each dispatch's number, the order (linked) and party, and the item count;
- the challan, invoice, transporter and vehicle, and who recorded it;
- voided dispatches are marked, with their reason.

It can be limited to the days between two dates, or show any day. The tab and the days are kept in the URL.

States covered: skeletons, "Nothing waiting to ship", "Nothing sent on these days", errors, and a later page failing. Checked on a phone and a desktop, in light and dark.

**Accounts queue.** This is not built yet; it waits on the backend (BE-022, below). Accounts' approval steps are already in their Approvals inbox.

## Discussion

**Why the Accounts queue isn't built.** The plan's Accounts queue is "orders waiting on the payment check". `GET /orders` can't filter on `approval_waiting_on`, and filtering on the screen would break paging and the count. No endpoint serves the `payments` module that RBAC.md lists either. Accounts loses nothing meanwhile: their steps arrive in the Approvals inbox with the payment-check remark. So the screen waits, and BE-022 asks the backend for two things:

- a `waiting_on` filter on `GET /orders`;
- a decision on payments.

**Why recording stays on the order page.** The queue doesn't copy the record form. The form needs the order's open quantities, and it already handles every rule and refusal there. The `?record=dispatch` link takes Dispatch straight to it, one click from the queue.

**Refreshing the queue.** Its query keys sit under the order lists' key. Recording a dispatch, voiding one, or approving an order already invalidates that key, so the queue refreshes with no extra wiring.

## Files changed

- `src/features/orders/api/orders.schemas.ts`: a dispatch keeps its order's number and party; `dispatchPageSchema`, `DispatchListParams`, `DISPATCH_PAGE_SIZE`.
- `src/features/orders/api/orders.api.ts`: `listDispatches`.
- `src/features/orders/api/orders.queries.ts`: `ordersToShipQueryOptions` and `dispatchListQueryOptions`, under `orderKeys.lists()`.
- `src/features/orders/components/dispatch-queue.tsx`: new, the queue.
- `src/features/orders/components/order-actions.tsx`: `?record=dispatch` opens the record form.
- `src/app/(app)/dispatch/page.tsx`, `loading.tsx`: the route.
- `src/components/layout/navigation.ts`: Dispatch queue is a link, for staff, with its description.
- `src/mocks/handlers/orders.ts`: `GET /dispatches`, filtered by order, partner and day.
- `src/features/orders/api/orders.test.ts`, `src/features/orders/components/orders-ui.test.tsx`: the tests.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: DISP-001 in progress; ACCT-001 waits on BE-022.
- `../docs/Backend-Tasks.md`: BE-022.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/dispatch/`: the records.

## Tests

**`src/features/orders/api/orders.test.ts`, `[DISP-001] listDispatches`:**

- newest first, with each dispatch's order number and party;
- the days are sent only when given;
- nothing comes back for days with no dispatch.

**`src/features/orders/components/orders-ui.test.tsx`:**

- `[DISP-001] Dispatch queue`:
  - the orders to ship, with their count and how much has gone;
  - the record link and its URL;
  - no recording for a manager;
  - the log, with the tab and days in the URL, "Nothing sent on these days", and "Any day".
- `[DISP-002]`: `?record=dispatch` opens the form for Dispatch, and does nothing for a manager.

**By hand, in Chromium on the mock backend, as Dispatch:**

- To ship and the log, on a desktop in light and on a phone in dark;
- Record a dispatch from the queue lands on the order with the form open;
- axe found nothing on either tab.
