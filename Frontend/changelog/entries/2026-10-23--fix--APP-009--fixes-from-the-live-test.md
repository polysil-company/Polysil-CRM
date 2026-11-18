---
date: 2026-10-23
type: fix
title: Fixes from the live test
dataIds:
  - APP-009
  - QUOT-004
  - APPR-002
  - MSTR-004
  - BOT-001
author: Nakul Srivastava
breaking: false
---

## Before

The live test of 22–23 Oct (PR #200, `Docs/Live-Test-Report.md`) ran 146 cases on the hosted app: 121 ✅, 14 ⚠️, 4 ❌, 7 ⛔. Thirteen of its 19 issues were the frontend's.

## Now

Each fix is listed by the report's issue number.

- **2 · A quotation needs an item.** Save stays off with "Add at least one item.", as on a new order. Before, an empty ₹0 draft could be saved and sent.
- **3 · Approval limits for approvers.** A state manager or anyone else who may approve now opens Approval limits, read-only. Only `masters.edit` changes them. The backend already served the ladders to every staff role.
- **4 · Pickers that failed say so.** If the category or unit list can't be loaded, the picker says "The categories couldn't be loaded", with **Try again**, instead of opening empty. The catalogue's Category filter says the same.
- **7 · Warehouse wording.** Over-committed stock reads "Warehouse short by 500 MTR", not "Warehouse short: -500 MTR available". Some stock left reads "only 40 NOS available".
- **8 · Terms-only edits.** Editing only a draft's customer or terms sends only the header. The history no longer adds "Items changed". A new sale type still re-saves the items, since it re-prices them.
- **11 · Ctrl + K.** When the search answer replaces the list, its first result is highlighted, so Enter opens it.
- **12 · Lists that fit.**
  - The Leads and Quotations lists fit their frame from 1280 to 1760 px.
  - **Leads:** Crops shows from 1760 px; Follow-up (empty until BE-002) from 1536.
  - **Quotations:** Type and Valid until show from 1760 px; Sent from 1536.
  - A `3xl` breakpoint (1760 px) is added to `tokens.css` for this.
- **13 · Freight in the builder.** The summary shows Freight on its own row from the `freight` the backend returns beside the totals. `QuoteTotals` has no freight field, so the row never appeared on the real backend.
- **14 · New lead form.** Fields are checked on the first **Create lead**, then as they change. The farmer's name, focused when the dialog opens, no longer turns red just for being left.
- **15 · Partner page for a field officer.** Each card asks only when the backend's rule lets the user read it. A field officer's partner page made three refused calls before.
  - The ledger and rating need `payments` view (`routers/payments.py`, `ratings.py`).
  - The credit also opens to staff who edit partners (`partner_credit_position`, migration 047), so a district or state manager keeps it.
- **16 · Rename toast.** It names the person as saved ("TEST Person 1b saved"), not as the page opened.
- **17 · Limit wording.** A changed limit says when it applies in its own words: the next order, discount request or refund.
- **18 · Approver wording.** "Waiting for an Admin sales…", "an MD": the article goes by sound.
- **19 · Tab icon.** The browser tab shows the droplet mark (`src/app/icon.svg`).

**Backend asks** in `docs/Backend-Tasks.md`:

- **BE-034:** redeploy the API from `integration`. This covers issues 1, 4, 5 and 9.
- **BE-035:** refuse a quotation with no items.
- **BE-036:** the dashboard's overdue count.
- **BE-037 and BE-038:** decisions on who may delete leads and on dispatches below zero stock.

The report gains a table of where each issue stands.

## Discussion

- **Approval limits:** the menu item keeps `masters` for administrators and adds `alsoTo: "approvers"`. A field officer, who approves nothing, still doesn't see it. The backend lets every staff role read the ladders, so this opens a page the API already serves and adds no rule.
- **Terms-only edits:** what the lines were when the draft opened is compared with what would be sent. With nothing changed at all, the lines are still sent, as before, so a save always answers with the document.
- **Lists that fit:** columns are hidden by breakpoint rather than shrunk, because the fill columns' floors keep names readable. The breakpoints were measured in the mock with the sidebar open.
- **Not changed:**
  - **Issue 6** (the dashboard's count) comes from the backend (BE-036).
  - **Issue 10:** the screens follow `/auth/me`, so a state manager sees Deleted leads wherever the backend grants `leads.delete` (BE-037).
  - **Issue 7:** whether a dispatch may take stock below zero is the client's decision (BE-038).

## Files changed

- `src/features/quotations/components/quotation-builder.tsx`: an item is needed to save; a terms-only edit sends only the header.
- `src/features/quotations/api/quotations.mutations.ts`: `useUpdateDraft` takes `lines: null`.
- `src/features/quotations/components/builder-parts.tsx`: freight from the preview's `freight`.
- `src/features/quotations/lib/quotation-lifecycle.ts`: `withArticle`.
- `src/features/quotations/lib/quotation-table-layout.ts`, `src/features/leads/lib/lead-table-layout.ts`: column breakpoints.
- `src/components/patterns/data-table/table-features.ts`: `2xl` and `3xl` hide-below classes.
- `src/styles/tokens.css`, `Docs/Design-System.md`: the `3xl` breakpoint.
- `src/components/layout/navigation.ts`: `alsoTo: "approvers"` on Approval limits.
- `src/components/layout/command-menu.tsx`: the first answer highlighted.
- `src/features/products/components/product-dialog.tsx`, `product-catalogue.tsx`: picker failures.
- `src/features/orders/lib/order-labels.ts`, `src/features/orders/components/order-detail.tsx`: `warehouseShortText`.
- `src/features/leads/components/new-lead-dialog.tsx`: validation on submit, then on change.
- `src/features/partners/components/partner-detail.tsx`: payments cards gated on `payments` view.
- `src/features/users/components/person-pages.tsx`: the saved name in the toast.
- `src/features/approvals/components/approval-limit-dialog.tsx`: `appliesFrom`.
- `src/app/icon.svg`: new.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: APP-009.
- `docs/Backend-Tasks.md`: BE-034 to BE-038.
- Records: `Docs/Live-Test-Report.md` (status table) and `Docs/Tested-Features.md`.

## Tests

New or extended, each named for its issue:

- `quotation-builder.test.tsx`, `[APP-009] The builder after the live test`: no items keeps Save off; a terms-only edit makes one PATCH and no lines PUT; freight shows from the preview's `freight` when `totals` has none.
- `navigation.test.ts`: a state manager opens Approval limits; a partner doesn't.
- `assistant.test.tsx`: after typing, the server's first answer is highlighted and Enter opens it. The test mirrors the live timing and fails without the fix.
- `order-labels.test.ts` (new): the shortfall wording.
- `quotation-lifecycle.test.ts`: `withArticle`.
- `approval-limits.test.tsx`: "It applies from the next order."
- `users-ui.test.tsx`: the toast names the person as saved.
- `partners-ui.test.tsx`: a field officer's partner page doesn't ask for the ledger, credit or rating. A state manager's asks for the credit only.
- `products-ui.test.tsx`: a failed category list says so, with **Try again**.
- `leads-ui.test.tsx`: the farmer's name isn't marked wrong for being left empty.

**Lists:** measured in the mock with Playwright at 1280, 1440, 1536 and 1760 px. Each table's width now equals its frame.

**To check by hand in the mock:**

1. As a state manager, open **Approval limits**: three ladders, read-only.
2. As Admin, open **New quotation** on a qualified lead: Save is off, with "Add at least one item."
