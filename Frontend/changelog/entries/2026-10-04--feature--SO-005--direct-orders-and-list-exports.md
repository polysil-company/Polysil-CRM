---
date: 2026-10-04
type: feature
title: Direct orders and list exports
dataIds:
  - SO-005
  - SO-006
  - LEAD-009
  - QUOT-013
author: Nakul Srivastava
breaking: false
---

## Before

An order could only be placed from an accepted quotation. The backend has always taken a direct order typed in line by line (`POST /orders` with `lines`) and a draft's lines replaced (`PUT /orders/{id}/lines`). The mock answered a direct order with "at least one accepted quotation", marked `TODO(SO-005)`.

A draft's items could not change once saved.

The lead, quotation and order lists had no download, though the backend serves all three (`GET /leads/export`, `/quotations/export`, `/orders/export`).

## Now

- **New order**, typed in without a quotation:
  - It starts from a qualified lead's page (or one further on), or from the orders list.
  - Items are picked and priced by the backend as they are typed, as in the quotation builder.
  - The party, mobile, GSTIN and address come from the lead, and the lead fixes the place of supply. An order started afresh asks where the goods go first, and nothing is priced until it is chosen.
  - It also takes the order type (commercial or industrial), delivery address, payment terms and remarks.
  - Save stays off until there is a place and at least one item, and says which is missing.
  - A price that moved since the preview is named on its line and priced again.
  - A new lead says it can't take an order yet; a role without `sales_orders.create` sees no access.
- **Edit items** on a draft order: its items and header in the same builder.
  - An order made from quotations keeps the party they fixed.
  - A submitted order can't be edited; the page says so and links to it.
- **Download Excel** on the lead, quotation and order lists: the rows the filters show, every page, under the backend's file name. More than 5,000 rows: "narrow the filters".
- The orders list's empty state mentions **New order**.

## Discussion

**Decisions:**

- **One pricing engine for both builders.** The quotation builder's line state, debounced preview and snapshot became `usePricedLines`. The items card, totals, warnings and text field became `builder-parts.tsx`. The quotation builder now uses them, and its 87 tests pass unchanged. Copying 780 lines would have let the two builders drift apart.
- **The preview waits for a place of supply.** `usePricedLines` sends nothing while the place is empty, so an order typed in afresh is never priced against the wrong state.
- **`partner_id` is the lead's dealer when there is one,** so the order is priced as the preview was. It is left out otherwise, which the backend reads as a direct sale by staff.
- **"Edit items" sits beside "Edit delivery and terms".** The quick dialog stays for the common case; the builder covers the items.
- **One `DownloadExcelButton`.** It replaces the inline copies in tasks and complaints, so all five lists say "Too many … to download" the same way.

**Still to build:** a consolidated order from several quotations on leads of one dealer, which needs several quotations picked at once (Plan §9.3).

**The mock:**

- `POST /orders` with `lines` prices them as the preview does. It refuses a lead that isn't qualified (`lead_not_open`), a missing party or place, and a changed price (`rate_changed`).
- `PUT /orders/{id}/lines` replaces a draft's lines.
- `PATCH` takes the party and order type; the party is refused on an order made from quotations.
- The three exports answer a dated workbook, built by one shared `mockWorkbook`.

## Files changed

- `src/features/quotations/hooks/use-priced-lines.ts`: new; the priced lines, from the quotation builder.
- `src/features/quotations/components/builder-parts.tsx`: new; the items card, summary, totals, warnings and text field.
- `src/features/quotations/components/quotation-builder.tsx`: uses them.
- `src/features/quotations/lib/builder-lines.ts`: `readAnyFields`, and the order's header fields for routing refusals.
- `src/features/orders/api/`:
  - `orders.schemas.ts`: `CreateDirectOrder`, `ReplaceOrderLinesRequest`, `OrderPartyRequest`; `PatchOrderRequest` takes the party and type.
  - `orders.api.ts`: `replaceOrderLines`, `exportOrders`.
  - `orders.mutations.ts`: `useSaveOrderDraft`.
  - `orders-direct.test.ts`: the API tests.
- `src/features/orders/components/`:
  - `order-builder.tsx`, `order-builder-pages.tsx`: new.
  - `order-builder.test.tsx`: the UI tests.
  - `order-actions.tsx`: Edit items.
  - `orders-toolbar.tsx`: New order and Download Excel.
  - `orders-table.tsx`: the empty state.
- `src/app/(app)/(sales)/sales-orders/new/`, `src/app/(app)/(sales)/sales-orders/[orderId]/edit/`: the routes.
- `src/features/leads/`: New order on a qualified lead; `exportLeads` and Download Excel.
- `src/features/quotations/api/quotations.api.ts`, `quotations-toolbar.tsx`: `exportQuotations` and Download Excel.
- `src/components/patterns/download-excel-button.tsx`: new.
- `src/features/tasks/components/all-tasks.tsx`, `src/features/complaints/components/complaints-list.tsx`: use it.
- `src/mocks/`: the direct order, replacing lines, the party and type in `PATCH`, the three exports, and `mockWorkbook`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SO-005 in progress; SO-006, LEAD-009, QUOT-013 registered.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/orders/`: the records.

## Tests

**`src/features/orders/api/orders-direct.test.ts`:**

- `[SO-005]`:
  - a direct draft on a qualified lead, priced, with no quotations;
  - `lead_not_open`, and a party without a name, are refused;
  - a draft's lines are replaced and its party changed;
  - a submitted order's lines are refused.
- `[SO-006] [LEAD-009] [QUOT-013]`: each list downloads as a dated workbook.

**`src/features/orders/components/order-builder.test.tsx`:**

- an item priced as typed, then saved as a draft that opens;
- an order started afresh needs a place before pricing;
- a new lead can't take an order;
- QA has no access;
- a draft's items are edited and every line saved;
- a submitted order can't be edited.

The quotation builder's and the tasks' existing tests pass on the shared pieces.

**By hand, in Chromium on the mock backend, as Admin:**

1. New order from a qualified lead: two items priced, saved, then the draft opened and edited.
2. New order afresh from the orders list.
3. Download Excel on the orders, leads and quotations lists; each saved its dated file.
4. The builder on a phone in dark mode.

axe found nothing on the builder, the draft, the order started afresh or the phone view.
