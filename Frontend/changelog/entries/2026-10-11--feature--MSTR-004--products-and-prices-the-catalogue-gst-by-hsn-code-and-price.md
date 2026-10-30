---
date: 2026-10-11
type: feature
title: "Products and prices: the catalogue, GST by HSN code, and price lists"
dataIds:
  - MSTR-004
  - MSTR-005
  - MSTR-006
author: Nakul Srivastava
breaking: false
---

## Before

The web app could only pick products inside a quotation (MSTR-003). Nothing let the client add a product, give it an HSN code and a GST slab, or set its price. The backend serves all of it (`backend/docs/api/products.md`, `pricing.md`, handover `products-and-pricing.md`). Without these screens a client going live on leads, quotations and orders could not put its own catalogue in.

## Now

**Admin → Products & prices** (`/products`) has three tabs, and the open tab is kept in the URL. Everyone on staff can read it. Admin-Sales and the MD can change it: they hold `products.edit` (the catalogue and tax) and `pricing.edit` (the price lists). Partners don't see it.

- **Products** (MSTR-004)
  - **The list.** A page of 50, with the total. Each row shows:
    - description and item code;
    - category, quotation block and unit;
    - HSN and GST slab, and MRP;
    - "No HSN", "2 stand-ins" and "Switched off" chips where they apply.
  - **Search and filters.** Search by description or item code. Filter by category, block and status (active by default, switched off, or all). Filters and page are kept in the URL.
  - **New product.**
    - Description. No two products may share one: "Another product already has this description."
    - Category and unit.
    - Quotation block (head unit, field, or either).
    - Optional item code, MRP and pack multiple, and "Eligible for subsidy".
    - What's missing is named before anything is sent.
  - **Opening a product** shows the same form.
    - Only what changed is sent. "Nothing changed yet" shows until something does.
    - A figure the backend still holds as a stand-in has a "Stand-in" chip, and setting it makes it the client's own.
    - **Switch off / Switch on.**
    - Read-only for anyone without `products.edit`.
- **Tax** (MSTR-005)
  - **On each product:**
    - the heading in force and its slab, or "No HSN code yet: quotations can't tax it";
    - its history, once it has changed;
    - a new HSN code from a date. The day the current heading started is refused, with what to do.
  - **The Tax rates tab:**
    - the rates in force today, or all of them, with "Starts later" and "Ended";
    - find a code by HSN;
    - **Set a rate**: HSN, a slab from the Council's list (0, 0.25, 3, 5, 12, 18, 28) and a start date, for every product under the code. **Change** opens it for that code.
- **Price lists** (MSTR-006)
  - **The list:** all, drafts or published. Each shows:
    - its phase: Draft, "Published, starts later", In force or Ended;
    - its scope: a state and a tier, or every one;
    - its dates;
    - how many rates it holds, and how many active products have none.
  - **New price list:** name, start date, an optional state and tier, and where the rates come from. It opens the new draft.
  - **The rate sheet** (`/products/price-lists/{id}`) has search and "Without a rate only".
    - On a draft, rates are typed in place and kept across pages and searches, with "2 unsaved changes" and **Discard**.
    - A rate with more than two decimals, or of 0, is named on its row, and **Save rates** stays off until it is fixed.
  - **Publish** needs saved rates. A list missing some asks you to tick "Publish without rates for N active products".
  - **A published list is read-only.** Its page says why. It can be **closed from a date** (its last day, forward only). It is corrected with **New list from this one**, which copies its scope and every rate into a new draft.
- **States:**
  - a skeleton for every list and the rate sheet;
  - empty, filtered-empty and past-the-end states;
  - a 404 for a list that doesn't exist;
  - refusals in words: 403, the 409s the backend names, and 422s on their fields.
- **Checked** on a phone in dark mode and on a desktop in light mode. axe found nothing.

## Discussion

- **Categories and units come from the catalogue itself,** read from every page of `GET /products`, active products and switched-off ones. `POST /products` takes only known codes, but nothing lists them. A free-text box would turn a typo into a refusal. Asked of the backend as **BE-024** (`GET /lookups/product-categories`, `/lookups/uoms`). Until then, a category no product uses yet can't be chosen.
- **Saving rates reads the list's own rates first.** `PUT /price-lists/{id}/items` replaces them all, so the screen lays the edits over them: a typed rate is set, a cleared one removed, the rest kept. This means a sheet bigger than one page is never cut down to the page on screen.
- **"New list from this one"** is how the backend says a published list is corrected. The screen creates a draft with the same scope, then copies the rates. Each step has its own idempotency key, so a retry never makes two drafts.
- **Closing asks for the last day in force,** and sends the day after, because the API's `effective_to` is exclusive.
- **Tax rates follow `products.edit`.** RBAC.md §6 has no tax module, and the backend checks `products` on `/tax-rates`.
- **Nothing is ever deleted.** A product is switched off; a list is closed.
- **The mock:** the product master has its own mock with the backend's rules (permissions, idempotency keys, the 409s, slabs, two decimals, forward-only closing). Quotations still price only the six products the quotation mock always had. A product added here lists, gets an HSN code and a rate, but the builder's live pricing doesn't know it. Against the backend both read the same tables.

## Files changed

- `src/features/products/`: new.
  - `api/`: schemas, API, queries, mutations, and `products.test.ts`.
  - `components/product-master.tsx`: the tabs.
  - `components/product-catalogue.tsx`: the Products tab.
  - `components/product-dialog.tsx`: add and edit, switch off, the HSN section.
  - `components/tax-rates-panel.tsx`: the Tax rates tab.
  - `components/price-lists-panel.tsx`: the Price lists tab, and the new-list and copy form.
  - `components/price-list-sheet.tsx`: the rate sheet, publish and close.
  - `components/pager.tsx`: Previous and Next for offset-paged lists.
  - `components/products-ui.test.tsx`: the UI tests.
  - `hooks/use-product-master-params.ts`: the tab and filters in the URL.
  - `lib/product-labels.ts`: labels, phases, dates and rate checks.
  - `lib/refusals.ts`: refusals in words.
- `src/app/(app)/products/`: the page, and `price-lists/[listId]`, each with a loading state.
- `src/components/layout/navigation.ts`: "Products & prices" under Admin.
- `src/lib/auth/permissions.ts`: the `products` and `pricing` modules.
- `src/mocks/`:
  - `data/products.ts` and `handlers/products.ts`: new;
  - `db.ts`;
  - `handlers/index.ts`;
  - `handlers/quotations.ts`: its `GET /products` moved to the products mock;
  - `data/permissions.ts`: staff can view products and pricing.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: MSTR-004, MSTR-005, MSTR-006.
- `../docs/Backend-Tasks.md`: BE-024.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/products/`: the records.

## Tests

**`src/features/products/api/products.test.ts`** (16):

- `[MSTR-004]`:
  - the active page, with stand-ins;
  - search, and switched-off products;
  - categories and units;
  - adding, and a description already in use;
  - confirming a stand-in and switching off;
  - an employee reads but can't add.
- `[MSTR-005]`:
  - a heading from a date closes the old one;
  - the same start date is refused;
  - a slab per code, and a slab the Council doesn't use is refused.
- `[MSTR-006]`:
  - the unpriced count;
  - a save keeps the list's other rates;
  - three decimals are refused;
  - a published list's rates never change;
  - publishing unpriced only when asked;
  - closing forward only;
  - an employee reads but can't publish.

**`src/features/products/components/products-ui.test.tsx`** (12):

- the catalogue with its chips;
- an empty search and its reset;
- what's missing, then a description in use;
- adding a product;
- a first HSN code and a confirmed MRP;
- read-only for an employee;
- the tax rates and setting one;
- the price lists with their phases;
- starting a draft;
- a bad rate blocks the save, then the save keeps the other rates;
- publishing unpriced only once ticked;
- a published list read-only.

**By hand, in Chromium on the mock backend** (`Docs/screenshots/products/`):

1. As Admin, desktop light:
   - the catalogue;
   - a product with stand-ins (MRP set);
   - a new product's mistakes, then a duplicate, then added;
   - an HSN code given to it;
   - tax rates, and setting 3917 at 18 %;
   - price lists;
   - the November dealers' draft: a three-decimal rate shown wrong, fixed, saved;
   - published without every rate;
   - the copy form.
2. The catalogue and a product with no HSN code, on a phone in dark mode.
3. As an Employee: no New price list, and the published list with no rate boxes.

axe found nothing on any of these.
