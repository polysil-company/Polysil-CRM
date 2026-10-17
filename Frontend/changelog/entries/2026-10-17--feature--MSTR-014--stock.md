---
date: 2026-10-17
type: feature
title: "Stock: what each warehouse holds, the ledger, recording stock, and the
  warehouses"
dataIds:
  - MSTR-014
  - MSTR-015
  - MSTR-016
author: Nakul Srivastava
breaking: false
---

## Before

The backend keeps stock by warehouse (handover `stock-contract.md`):

- receipts and corrections;
- dispatches taking stock out;
- what open orders have committed;
- the default warehouse.

None of it had a screen.

## Now

- **Operations → Stock** (`/stock`), for every staff role (`stock.view`); dealers get none. The tab is in the URL.
- **Stock (MSTR-014):** each product in each warehouse, with on hand, committed and available.
  - Committed is what submitted, approved and partly dispatched orders still owe.
  - A negative available reads "Short by …" in red.
  - Filters: warehouse, product, and **Short only**.
  - On a phone the table scrolls sideways and takes keyboard focus.
- **Ledger (MSTR-014):** every movement, newest first: received, correction, dispatched or dispatch undone. Each shows its product, warehouse, reference, dispatch and order, who recorded it, and a signed quantity, with minus in red.
- **Record stock (MSTR-015, `stock.create`: Dispatch and Admin):**
  - the warehouse (the default first), **Stock received** or **A correction**, a reference ("Opening" for an opening balance), a note, and a quantity per product;
  - received must be more than 0, and a correction is not 0 (a minus takes stock off);
  - the backend's refusals are in words: below zero (`negative_stock`), a switched-off warehouse or product, and a quantity with decimals on a whole-unit product, which is marked on its line.
- **Warehouses (MSTR-016, `stock.edit`: Admin):** add a warehouse, change its code or name, **Make default**, and switch it off or on.
  - A taken code is refused on its field.
  - The default can't be switched off until another is the default (`default_warehouse`).
  - The first warehouse added is the default.
- Every list has its loading skeleton, empty state and error with retry.
- Walked through in the mock, with axe finding nothing:
  - Dispatch on a desktop in light mode;
  - Admin on Warehouses;
  - a field officer on a phone in dark mode.

## Discussion

- **A new permission module, `stock`,** as the backend checks it:
  - every staff role views;
  - Dispatch and Admin create;
  - Admin edits.
- **The order side is item 28b,** in its own pull request: "Order to", availability per line, the order's warehouse and the dispatch's. The order contract gains `warehouse` now, so the mock can count what each warehouse has committed.
- Built to the backend's contract and checked against the mock only; not yet checked on staging.

## Files changed

- `src/features/stock/` — the contract, API, queries, mutations, labels, the page, the stock list, the ledger, the record form, warehouses, the warehouse select, and tests.
- `src/app/(app)/stock/page.tsx` — the route.
- `src/components/layout/navigation.ts` — Stock in Operations.
- `src/lib/auth/permissions.ts` — the `stock` module.
- `src/features/orders/api/orders.schemas.ts` — `warehouse` on an order (DISP-003).
- `src/mocks/` — three warehouses, opening balances and two movements, all seven stock endpoints, and the grants.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — MSTR-014…016 and DISP-003.

## Tests

- `src/features/stock/components/stock.test.tsx` — 9 tests:
  - contract: `[MSTR-014] Stock`, `[MSTR-015] Recording stock`, `[MSTR-016] Warehouses`;
  - labels: `[MSTR-014] Stock labels`;
  - screens: `[MSTR-014] StockPage`.
- By hand:
  1. As Dispatch, open Operations → Stock, tick Short only, and record stock received.
  2. As Admin, open Warehouses and make Rajkot the default.
