---
date: 2026-10-17
type: feature
title: "Stock on orders: Order to, availability per line, and where a dispatch
  left from"
dataIds:
  - DISP-003
author: Nakul Srivastava
breaking: false
---

## Before

Stock had its own screens (#162), but an order didn't say which warehouse served it or whether the warehouse had enough. A dispatch didn't say where the goods left from, and took no stock out.

## Now

- **Order to (DISP-003).** Staff with stock access pick the warehouse on a new or draft order; the default is shown as chosen.
  - It is sent as `warehouse_id` only when it differs from the default; a changed draft sends it with the header.
  - A dealer never sees it: its order comes from the default, and the backend refuses a choice (422).
- **Availability on the order form:** under the summary, each line's product reads "850 available", or "Short by 50" in amber when the line wants more. It is read again when the warehouse or the lines change.
  - It warns and never blocks the order.
- **On the order page:**
  - "Order to" names the warehouse.
  - Each open line reads its available stock, amber with "Warehouse short" when the warehouse is over-committed.
  - Nothing shows for a shipped line or for someone without stock access.
- **Recording a dispatch:** **Left from** picks the warehouse, defaulting to the order's. The dispatch names it, and the stock comes out of it.
  - Voiding a dispatch puts the stock back.
  - The ledger lists both movements, with the dispatch and the order.
- Walked through in the mock, with axe finding nothing: Admin on the order form, and Dispatch on an approved order and its dispatch form, both on a desktop in light mode.

## Discussion

- **Stacked on #162,** the stock screens. Merge #162 first, then retarget this one to `integration`.
- **The default warehouse is "no choice".** Picking the default sends nothing, so an order follows the default if Admin moves it.
- **Committed counts the order itself,** so "short" on the order page means the warehouse is over-committed, as the contract says, not that this line alone is short.
- Built to the backend's contract and checked against the mock only; not yet checked on staging.

## Files changed

- `src/features/orders/api/orders.schemas.ts` — `warehouse` on an order and a dispatch, `stock` on a line, and `warehouse_id` on create, patch and dispatch.
- `src/features/orders/components/order-builder.tsx` — Order to and the availability panel, staff with stock access only.
- `src/features/orders/components/order-detail.tsx` — Order to, and each open line's stock.
- `src/features/orders/components/record-dispatch-form.tsx`, `order-dispatches.tsx` — Left from, and the warehouse on each dispatch.
- `src/features/stock/components/order-stock.tsx` — the Order to field, the Left from field and the availability panel.
- `src/mocks/handlers/stock.ts`, `orders.ts` — the warehouse choice, line stock on every read, and dispatch movements.

## Tests

- `src/features/stock/components/order-stock.test.tsx` — 6 tests:
  - contract: `[DISP-003] Stock on orders`;
  - screens: `[DISP-003] Stock on order screens`.
- The order suites still pass.
- By hand:
  1. As Admin, start a new order, add a large quantity and watch the stock panel.
  2. As Dispatch, open an approved order, read each line's stock, and record a dispatch from Rajkot.
  3. See it in Operations → Stock → Ledger.
