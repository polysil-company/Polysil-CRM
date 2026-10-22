---
date: 2026-10-22
type: feature
title: The backend's answers to BE-023 to BE-030, wired in
dataIds:
  - MSTR-004
  - SUBS-005
  - SCHM-002
  - DOC-001
  - MSTR-009
  - SO-011
  - TASK-009
  - AUTH-002
  - MSTR-017
author: Nakul Srivastava
breaking: false
---

## Before

The backend shipped eight answers to the frontend's asks in #190 (`docs/Backend-Tasks.md`, BE-023 to BE-030). Until then the screens worked around each gap:

- the lead's subsidy card filtered applications itself;
- the product form read every product to learn the categories and units;
- schemes read each target's name from its own record, one call per target;
- the document type picker offered a dealer application's types on every record;
- Masters couldn't show a row's order or quality;
- Place order listed quotations already on an order;
- a dealer's every page asked `/tasks` and got a refused request.

## Now

- **BE-023 · The lead's subsidy application** comes from `GET /subsidy-applications?lead_id=`. The card no longer filters the rows itself. An empty answer means none the user can see, so Start still handles `already_forwarded`.
- **BE-024 · The product form's pickers** come from `GET /lookups/product-categories` (by name) and `GET /lookups/uoms` (with each unit's decimals).
  - Each picker offers the active rows, plus a switched-off one only to a product that already has it.
  - The catalogue's Category filter lists every category too.
  - Warranty periods now offer every active category, not only those already used.
- **BE-027 · A scheme's targets** show the names the backend sends, with no extra calls. A target outside the user's scope shows its kind and a short id.
  - **Product category** can now be added as a target: tick boxes from the categories, sent by id.
  - The form still sends `targets` on an edit only when they changed, as the backend asks.
- **BE-025 · The document type picker** asks for the record's own types (`GET /documents/types?record_type=`). A lead, quotation, order or dispatch no longer offers the GST certificate or the PAN card.
- **BE-026 · Masters lists:**
  - sources and lost reasons show their **Order**, and lost reasons their **Kind**;
  - those who may edit masters also see a source's **Quality**, and get **Edit** for the order and the quality. Only what changed is sent, within ±1,000,000 and 0 to 1.
- **BE-029 · Place order's other quotations** come from `GET /quotations?orderable=true`: accepted, current and on no live order. A `409 quotation_on_order` is still handled, for an order the user can't see.
- **BE-030 · A dealer's Tasks item** follows `features.tasks_for_dealers` on `GET /auth/me`, so partner pages no longer make a refused `/tasks` call.
- **BE-028** needed nothing built.

## Discussion

- **The mock follows each answer:**
  - the categories and units are the backend's seeds, with the mock catalogue's own unit codes (NOS, MTR at two decimals, SET);
  - warranty terms use the same category ids;
  - sources carry the seeded quality and order, and quality is null for those without `masters.edit`;
  - scheme targets are named;
  - `/auth/me` carries the switch.
- **"Won" reasons:** the backend lists none yet (GAP-513), so every lost reason shows "Lost".

## Files changed

- `src/features/subsidy/api/` — the `lead_id` filter is the backend's.
- `src/features/products/` — the two lookups, their queries, the form's pickers and the catalogue filter.
- `src/features/warranty/components/warranty-terms-panel.tsx` — every category.
- `src/features/schemes/` — target names from the scheme; product category targets; the per-target calls removed.
- `src/features/documents/` — types by record.
- `src/features/lookups/api/lookups.schemas.ts`, `src/features/masters/` — order, quality and kind; the Edit dialog.
- `src/features/quotations/api/`, `src/features/orders/components/consolidate-quotations.tsx` — `orderable`.
- `src/features/session/api/session.schemas.ts`, `src/features/tasks/hooks/use-dealer-tasks.ts` — the switch on `/auth/me`.
- `src/mocks/` — the lookups, record types, row fields, named targets, `orderable` and the switch.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`, `Docs/Plan.md`, `Docs/Tested-Features.md`.

## Tests

- `products.test.ts`: the categories with ids, and the units with decimals; a code that isn't one refused.
- `schemes.test.tsx`: a scheme's targets named; a product category added as a target, by id.
- `documents.test.ts`: a lead's types without a dealer's, and a dealer application's five and Other.
- `masters-ui.test.tsx`: order and quality shown; Edit refusing a quality over 1, then saving only the quality; quality hidden and Kind shown without `masters.edit`; only a changed field sent.
- `quotations.test.ts`: `orderable` lists only free accepted quotations, and is sent as `orderable=true`.
- `session.schemas.test.ts` and `dealer-tasks.test.tsx`: the switch read from `/auth/me`, off when missing, and no `/tasks` call to find out.
- Existing suites updated for the new fields, the unit labels and the warranty categories.
