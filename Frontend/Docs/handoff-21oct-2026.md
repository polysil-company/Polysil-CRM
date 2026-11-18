# Handoff, 21 Oct 2026: frontend work for another agent

Read `Frontend/AGENTS.md` first. It holds the house rules: the records, Data-IDs, changelog entries, `npm run verify` and `npx prettier --check .`.

## Rules for every item

- **Branches:** branch from `integration`. One PR per item, with the base set to `integration`.
- **Code:**
  - strict TypeScript, with no `any` and no `as`;
  - explicit return types;
  - Zod at the API boundary, in each feature's `api/*.schemas.ts`;
  - Tailwind tokens only.
- **Mock:** every new endpoint gets an MSW handler in `src/mocks/handlers/*` and a Vitest test.
- **Business rules:** don't invent them. If the backend is missing something, add a `BE-NNN` entry to `docs/Backend-Tasks.md` and stop there.
- **Release menu:** don't touch `RELEASED_NAV` in `backend/scripts/deploy_staging.py`.
- **Backend reference:** contracts are in `backend/docs/api/*.md`.

---

## 1. HSN missing on the New product form (bug, do first)

- **Where:** `src/features/products/components/product-dialog.tsx`.
  - Line 476: `{product === null ? null : <TaxHeading … />}`. The HSN section renders only for a product that already exists.
  - Line 145: `createOf(draft)` sends no HSN.
  - The submit is at lines 200–228.
- **Why it can't just go in create:**
  - `POST /products` (`ProductCreate` in `backend/docs/api/products.md`) has no `hsn_code` field.
  - HSN is set only through `PUT /products/{id}/hsn`, with body `{ hsn_code: 4–8 digits, effective_from: date }`.
- **Fix:**
  - Add an optional "HSN code" field and a "From" date to the New product form. Validate with `/^\d{4,8}$/`, as in `tax-rates-panel.tsx`. The date defaults to today.
  - On submit, create the product first. If an HSN was entered, call `useAssignHsn()` with the new id.
  - **If the HSN call fails after the product was created:**
    - keep the product;
    - show a toast: "Product added, HSN not set: <reason>";
    - leave the dialog open in edit mode on that product, so the user can retry in `TaxHeading`.
  - Give the HSN request and the create request separate idempotency keys.
- **Tests:**
  - create with an HSN: both calls are made, and the catalogue loses its "No HSN" badge;
  - create without an HSN: only `POST` is made;
  - the HSN call fails: the product exists, the error shows, and the dialog switches to edit mode.

## 2. FS-069: per-line GST slab and freight (biggest item)

Docs: `backend/docs/api/pricing.md` (from line 298, and the rule at about line 350), plus `quotations.md`, `orders.md` and `approvals.md`.

- **Scope:** commercial and industrial sales only.
- **Slab dropdown on each line** in `quotations/components/quotation-builder.tsx` and `orders/components/order-builder.tsx`:
  - get the options once per screen from `GET /pricing/gst-slabs`, where the admin setting `gst_slab_choices` defaults to 0, 5, 18 and 40;
  - preset each line to its `hsn_slab`, even when that slab isn't in the list;
  - send `gst_slab` only when the user picked a slab.
- **Optional freight** (an amount, with an optional slab) on create, PATCH and lines-replace:
  - freight with no slab takes the highest slab among the lines;
  - `totals.taxable` and `totals.total` include freight; `gross` and `discount` don't.
- **Detail pages and PDF preview:**
  - mark a line whose `gst_slab_chosen` differs from its `hsn_slab`;
  - show freight in the totals.
- **Approvals:** show `gst_changed_lines`.
- **Errors**, each shown on its field: 422 `gst_choice_not_allowed`, `gst_slab_not_offered`, `freight_not_allowed`, `freight_without_lines` and `freight_amount_invalid`.

## 3. Backend answers that are ready to wire (BE-023 to BE-030, all ticked in `docs/Backend-Tasks.md`)

- **BE-023:** the lead's subsidy card, `subsidy/components/lead-subsidy.tsx`, reads `GET /subsidy-applications?lead_id=` (SUBS-005).
- **BE-024 and BE-027:**
  - the product form's category and unit pickers use `GET /lookups/product-categories` (with id) and `GET /lookups/uoms` (with decimals);
  - schemes: show the target's `name`, and send targets on PATCH only when they changed.
- **BE-025:** the document-type picker reads `GET /documents/types?record_type=`.
- **BE-026:** Masters lists show and edit `sort_order` and `kind`, and `quality`, which is editable only with `masters.edit`.
- **BE-029:** `orders/components/consolidate-quotations.tsx` lists from `GET /quotations?orderable=true`. Still handle 409 `quotation_on_order`, and keep `consolidate.test.tsx` green.
- **BE-030:**
  - `tasks/hooks/use-dealer-tasks.ts` (`useDealerTasksOn`) reads `features.tasks_for_dealers` from `/auth/me`;
  - this replaces the `/tasks` probe, so partner pages stop logging a refused request.
- **BE-028:** nothing to build.

## Waiting, don't build

- **BE-031:** the complaint PDF on the backend. The frontend is already done (CMPL-013).
- **Website:** waiting on content from the client.
- **Android tracking app** (Capacitor): needs its own plan.
- **Staging check:** needs credentials.
