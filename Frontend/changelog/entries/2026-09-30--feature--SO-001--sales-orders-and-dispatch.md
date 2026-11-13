---
date: 2026-09-30
type: feature
title: "Sales orders and dispatch: place an order from a quotation, follow its
  approval, record what left"
dataIds:
  - SO-001
  - SO-002
  - SO-003
  - SO-004
  - DISP-002
  - APPR-001
author: Nakul Srivastava
breaking: false
---

## Before

Sales orders was a "coming soon" page. An accepted quotation could not become an order, the approvals inbox decided orders that had no page ("Order details open from Sales orders once that module is built"), and the mock's order rows were stand-ins with no order behind them.

The frontend also asked for permission modules the backend does not have: `orders` and `approvals`. The backend's are `sales_orders` and `dispatch`, and approving is the `approve` action on `sales_orders` or `quotations` (`backend/docs/architecture/RBAC.md` §6). On the real backend, Sales orders and Approvals would have stayed hidden from everyone.

## Now

**The list (SO-001)** — `/sales-orders`: number (or "Draft order"), the dealer or "Direct sale", "Provisional", the party, the status with whom it waits on ("Waiting on Accounts"), how much has shipped (a share and a thin bar), type, owner, created, total. Filters by several statuses, one type and **Only my orders**, and a search by number, party or mobile, all in the URL. States: skeleton, "No sales orders yet" (orders come from an accepted quotation), nothing matches, a page link that no longer works, an emptied page, errors.

**The order page (SO-002)** — `/sales-orders/{id}`:

- The lines with ordered, sent, open and short once approved (phone: one card per line), and totals with CGST and SGST or IGST, as the backend prints them.
- **The approval chain** step by step: the managers by value, then Accounts, then Dispatch. Each step says approved, returned, "Waiting now" or next, who decided and when, their remark, and when a higher manager covered it. Those who decide get **Open approvals**.
- **Dispatches**, newest first: challan and invoice with dates, transporter, vehicle, who recorded it and each item's quantity. A voided one stays, struck through, with the reason.
- Party, the quotations it came from, delivery address, payment terms ("recorded, not checked"), place of supply, seller, dates, remarks, and its **history**.
- **Open PDF** once approved ("Preparing PDF…" while it renders; the page checks again by itself).
- Notices: returned with the reason, cancelled or closed short with the reason, indicative pricing, no mobile for the customer's confirmation, the PDF failed.

**Placing an order (SO-003)** — an accepted, current quotation has **Place order** for roles with `sales_orders.create`: order type (commercial or industrial; the others are not built on the backend), delivery address (the party's by default), payment terms, remarks. The draft opens. A quotation already on a live order shows **Open order** instead, so `409 quotation_on_order` is never a surprise. A draft's delivery, terms and remarks can be changed; a draft that was never submitted can be deleted by a holder of `sales_orders.delete`, and a numbered one is cancelled instead.

**Submit and cancel (SO-004)** — **Submit for approval**, or **Submit again** after a return: the order gets its number and starts its chain; the dialog says what happens. **Cancel** needs a reason: the owner while it is a draft or waiting, a holder of delete once approved, nobody once something has shipped (close it short instead).

**Dispatch (DISP-002)**, for Dispatch (`dispatch.create`/`edit`):

- **Record a dispatch:** each open item's quantity (or **Everything open**), when it left (not in the future), challan, invoice, transporter, vehicle. Refused on the field before it is sent: nothing entered, more than is open, decimals on a whole-unit item. The backend's own refusals land on the same fields. An invoice dated before its challan, or an invoice number already used, is recorded with a warning toast.
- **Void a dispatch** with a reason (its quantities are open again) and **close the rest short** with a reason.

**Every action** retries safely with its Idempotency-Key and sends the status the screen showed. When someone else moved the order first, the dialog closes, a toast says what happened, and the page shows the latest; any other refusal stays in the dialog, in words ("Nobody can approve this order", "Prices changed since the draft was saved").

**Approvals (APPR-001)** — order rows have **Open the order**. Order steps arrive one at a time, as on the backend: the next joins its inbox when the one before is approved. Accounts and Dispatch see only their own steps, and Accounts needs a remark on every decision (BE-018).

**Permissions** now use the backend's codes: Sales orders follows `sales_orders`, and Approvals shows to whoever holds `sales_orders.approve` or `quotations.approve` (`canApprove`, `useCanApprove`). The mock's roles follow RBAC.md: field staff and partners view, create and edit orders; managers also approve; Accounts views and approves; Dispatch holds `dispatch` view, create, edit and approve, and approves orders.

**The mock backend** now has real orders: eight made from the seeded accepted quotations, in every state (partly and fully dispatched, waiting at District and further up, approved, returned with a reason, cancelled, closed short), with their chains, dispatches and history, all in the past. It follows the backend's rules and codes: `quotation_on_order`, `quotation_not_accepted`, `quotations_disagree`, `order_not_draft`, `order_was_submitted`, `order_dispatched`, `order_not_cancellable`, `order_not_dispatchable`, `over_open_quantity`, `unit_precision`, `duplicate_line`, `dispatch_voided`, `order_closed`, `status_changed`, `remark_required` and `self_approval`. An approval at the last step approves the order and its PDF is ready a few seconds later.

**Shared pieces:** the notice box and the PDF link button moved to `components/patterns` (`Notice`, `PdfLinkButton`), and the quotation page uses them too. "(optional)" on field labels is now `text-muted-foreground`, since the subtler tone failed contrast in dark dialogs (axe).

## Discussion

- **Quotation first, then order.** The backend makes an order from accepted quotations or from typed-in lines. This slice builds the first — the path the sales team walks every day. The direct order builder, the consolidated dealer order and the approval limits screen are the next pull request (SO-005, APPR-002; Plan §9.3).
- **Finding a quotation's order.** List rows carry no quotation ids, so the quotation page lists its lead's orders and reads each live one (up to ten) to find the match. One `GET /orders?quotation_id=` would do: asked as **BE-019**, `TODO(SO-003)` in `place-order.tsx`.
- **The screen never totals money.** Every figure is the backend's; the "sent" share on the order page is a count of quantities, not money.
- **Dispatch quantity checks are a courtesy.** The form checks against the open quantity and the unit's decimals so mistakes show at once; the backend checks the same and its answers are mapped onto the same fields.
- **Void stays on a dispatched order.** The backend refuses a void only on a closed order (`409 order_closed`), so Dispatch can undo a mistaken last dispatch.
- **Not checked on the dev API yet** (Plan §9.1): the flows are tested against the mock, which follows the contract; a hand check on the dev API is due before staging.

## Files changed

- `src/features/orders/api/` — `orders.schemas.ts` (the contract, the header and remark forms, `dispatchFormSchemaFor`), `orders.api.ts`, `orders.queries.ts`, `orders.mutations.ts`
- `src/features/orders/lib/` — `order-labels.ts`, `order-lifecycle.ts` (what can be done, refusals in words, history lines), `order-table-layout.ts`
- `src/features/orders/hooks/` — `use-order-list-params.ts`, `use-order-actions.ts`
- `src/features/orders/components/` — `orders-table.tsx`, `orders-columns.tsx`, `orders-toolbar.tsx`, `order-status-badge.tsx`, `order-detail.tsx`, `order-approval.tsx`, `order-dispatches.tsx`, `order-history.tsx`, `order-actions.tsx`, `order-action-dialog.tsx`, `order-dialog-shared.tsx`, `record-dispatch-form.tsx`, `place-order.tsx`
- `src/app/(app)/(sales)/sales-orders/` — the list (replacing the placeholder), `loading.tsx`; `[orderId]/page.tsx`, `loading.tsx`, `not-found.tsx`
- `src/components/patterns/notice.tsx`, `pdf-link-button.tsx` — new, shared; `src/features/quotations/components/quotation-detail.tsx`, `quotation-pdf-button.tsx` use them
- `src/features/quotations/components/quotation-actions.tsx` — Place order / Open order on an accepted quotation
- `src/features/approvals/components/approvals-inbox.tsx` — Open the order; `approval-labels.ts` — the Accounts remark rule by its role code; `approvals.mutations.ts` — a decision re-reads the order it decided and the order lists
- `src/lib/auth/permissions.ts` — `sales_orders` for `orders`, no `approvals` module, `canApprove`; `src/components/layout/navigation.ts`, `app-sidebar.tsx`, `src/features/session/hooks/use-session.ts` (`useCanApprove`), `src/features/leads/components/sales-tabs.tsx`
- `src/mocks/data/orders.ts`, `src/mocks/handlers/orders.ts` — new; `data/approvals.ts` — order steps from real orders, one at a time, `seq`; `handlers/approvals.ts` — the chain moves on, `remark_required`, `self_approval`; `data/permissions.ts` — RBAC.md's grants; `data/reference.ts`, `db.ts`, `handlers/index.ts`, `handlers/quotations.ts` — registered
- `src/features/quotations/components/quotation-builder.tsx`, `quotation-action-dialog.tsx`, `src/features/approvals/components/approval-decision-dialog.tsx` — "(optional)" contrast
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — SO-001…004, DISP-002
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `../docs/Backend-Tasks.md` (BE-019), `Docs/screenshots/orders/`
- `e2e/smoke.spec.ts` — sales orders, with axe

## Tests

- `src/features/orders/api/orders.test.ts` — `[SO-001]` newest first with the count, status, type and search filters, the shipped share; `[SO-002]` the document, chain, dispatches and history, 404; `[SO-003]` a draft from an accepted quotation once (`quotation_on_order`), `quotation_not_accepted`, the header and `status_changed`, delete only never-submitted and only with delete; `[SO-004]` the whole chain with Accounts' remark (`remark_required`), a return to draft with the reason, cancel and `order_dispatched`; `[DISP-002]` over the open quantity, a future time, record, void, close short, `dispatch_voided`, refused without dispatch
- `src/features/orders/api/orders.schemas.test.ts` — `[DISP-002]` the dispatch form: at least one item, not in the future, open quantity, unit precision, a number
- `src/features/orders/lib/order-lifecycle.test.ts` — `[SO-004]` the actions by status and permission, refusals in words, `[SO-002]` history lines, `[SO-001]` labels
- `src/features/orders/components/orders-ui.test.tsx` — `[SO-001]` the list, filters from the URL, empty; `[SO-002]` a manager sees the chain and dispatches without dispatch actions; `[SO-004]` a returned order submitted again; `[DISP-002]` the dispatch form's checks, then recorded; `[SO-003]` place an order from a quotation, and Open order when it already has one
- `src/features/approvals/api/approvals.test.ts` — the reason to reject is `remark_required`, as the backend answers
- `src/lib/auth/permissions.test.ts`, `src/mocks/data/permissions.test.ts` — the backend's module codes and who approves
- `e2e/smoke.spec.ts` — `[SO-001]` the list opens an order with its chain and dispatches; axe finds no violations; desktop and phone
- By hand (`npm run dev`): as State Manager, open Sales orders; filter Waiting for approval; open the returned draft, edit its delivery, submit it again; approve its first step in Approvals. As Dispatch Manager (Preview as role), open the partly dispatched order, record with nothing then too much, then Everything open; void it; close short. As Employee on a phone, open an accepted quotation and Place order. At 360px and on a wide screen, light and dark; axe finds nothing.
