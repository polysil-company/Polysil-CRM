---
date: 2026-10-14
type: feature
title: The Accounts queue, and the order counts behind its badge
dataIds:
  - ACCT-001
author: Nakul Srivastava
breaking: false
---

## Before

"Accounts queue" sat in the menu marked "Soon". The backend finished it in BE-022 (`accounts-queue-order-names.md`):

- `waiting_on` on `GET /orders`, `/orders/stats` and `/orders/export`;
- `GET /orders/stats` itself.

Accounts found their orders only through the Approvals inbox.

The menu item also asked for an `accounts` permission. The backend has no such module: the Accounts role holds `payments` (RBAC.md §6.2). So on the real backend the item could never have appeared.

## Now

- **The Accounts queue,** at `/accounts`.
  - **The list:** every submitted order whose next approval step is Accounts' payment check. Each row shows its number (linked to the order), the party and dealer, type, owner, when it was submitted, and its value.
  - **Deciding:** **Decide in Approvals** for those who decide.
  - **Above the list:** "1 order waits on Accounts' payment check", and **Download Excel** for the queue.
  - **States:** skeleton, "Nothing waits on Accounts" (saying when an order arrives), an error with a reference, a later page failing while the rows stay.
- **The sidebar badge** on Accounts queue: the waiting orders, from `GET /orders/stats`'s `waiting_on.account_manager`.
  - It is checked again each minute.
  - It refreshes whenever an order or an approval changes.
- **Who sees it:** whoever may view payments, which is Accounts and Admin. A field officer has no menu item, and the page refuses them (APP-006).
- **The permission module** is `payments`, as the backend names it.
  - The mock's Accounts role holds payments view, create, edit and approve, as RBAC.md says.
  - A payment's documents follow `payments.edit`, as the backend's do.
- Checked on a desktop in light mode and a phone in dark mode. axe found nothing.

## Discussion

- **Built like the Dispatch queue,** as rows rather than a table. "Show more" and the list skeleton now live in `queue-parts.tsx`, shared by both queues.
- **Deciding stays in Approvals.** The queue sends each order there rather than repeating the decision dialog.
- **Recording a payment** ("What Accounts records" in the handover) needs the payments screens, plan item 26. The queue has no such button yet.
- **The badge reads the stats without `waiting_on`,** as the handover says. Its key sits under the order lists, so every write and approval decision that refreshes the lists refreshes it too.
- **Stacked on #125,** which reworked the same order list parameters and mock filter. Merge #125 first, then retarget this PR to `integration`.

## Files changed

- `src/features/orders/api/orders.schemas.ts`: `waitingOn` on the list parameters; `orderStatsSchema`; `ACCOUNTS_ROLE`.
- `src/features/orders/api/orders.api.ts`: `getOrderStats`; `waiting_on` on the list and export.
- `src/features/orders/api/orders.queries.ts`: `orderStatsQueryOptions`, `accountsQueueQueryOptions`, `ACCOUNTS_QUEUE`.
- `src/features/orders/components/accounts-queue.tsx`: new, the queue.
- `src/features/orders/components/queue-parts.tsx`: new, "Show more" and the skeleton, moved from `dispatch-queue.tsx`.
- `src/app/(app)/accounts/page.tsx`: new, the route.
- `src/components/layout/navigation.ts`, `app-sidebar.tsx`: the live menu item and its badge.
- `src/lib/auth/permissions.ts`, `src/mocks/data/permissions.ts`, `src/mocks/handlers/documents.ts`: `payments` replaces `accounts`.
- `src/mocks/handlers/orders.ts`: `waiting_on` in the shared filter; `GET /orders/stats`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: ACCT-001 in progress, with its endpoints.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/accounts/`: records and screens.

## Tests

- `src/features/orders/api/orders.test.ts`, `[ACCT-001] Order stats and the Accounts queue`:
  - every status counted, and the one order waiting on Accounts;
  - the list filtered with `waiting_on=account_manager`.
- `src/features/orders/components/accounts-queue.test.tsx`, `[ACCT-001] AccountsQueue`:
  - the row, its link and "Decide in Approvals";
  - the count line and Download Excel;
  - the empty queue.
- `src/components/layout/navigation.test.ts`, `[APP-006]`: `/accounts` opens to Accounts and Admin, not to a field officer or a dealer.
- `src/mocks/data/permissions.test.ts`: Accounts approves on `payments`.
- Walked through in the mock:
  - as Accounts: desktop light and phone dark, with the sidebar badge reading "Waiting on Accounts: 1";
  - as a field officer: refused, with no menu item.
