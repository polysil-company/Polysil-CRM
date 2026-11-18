---
date: 2026-10-21
type: fix
title: An HSN code on the New product form
dataIds:
  - MSTR-005
  - MSTR-004
author: Nakul Srivastava
breaking: false
---

## Before

The New product form had no HSN code. The Tax section, where a heading is set, showed only once a product existed, and `POST /products` takes no `hsn_code` (`ProductCreate` in `backend/docs/api/products.md`). So a new product always reached the catalogue with "No HSN". Quotations couldn't tax it until someone opened it again to set one.

## Now

- **New product** has an optional **HSN code** with a **From** date, which defaults to today. The code is four to eight digits, as on the Tax rates tab; a bad one is named before anything is sent.
- **Adding the product with an HSN** makes two requests, each with its own idempotency key: first `POST /products`, then `PUT /products/{id}/hsn` for the new product. Without an HSN, only the product is created.
- **When the heading is refused after the product was made:**
  - the product stays;
  - a toast says "Product added, HSN not set: <reason>";
  - the dialog stays open on the new product, in edit mode, with its Tax section to set the code again.
- Checked on a phone in dark mode and a desktop in light mode. axe found nothing.

## Discussion

- **Two requests, not one.** The backend sets a heading only through `PUT /products/{id}/hsn`, which keeps its history with dates. Creating the product first means a refused heading never costs the product: there is nothing to undo, and the person tries the code again where headings are set.
- **Separate keys.** A retried save after a failure must not replay the product's create under the heading's key, or the other way round.

## Files changed

- `src/features/products/components/product-dialog.tsx` — the HSN and From fields on a new product, the create-then-heading save, and edit mode on the new product when the heading fails.
- `src/features/products/components/products-ui.test.tsx` — three tests.
- `Docs/Tested-Features.md`, `Docs/screenshots/products/` — the story and screens.

## Tests

- `src/features/products/components/products-ui.test.tsx`, `[MSTR-005] A new product's HSN code`:
  - with an HSN: `POST` then `PUT …/hsn`, and the new row has no "No HSN" badge;
  - a bad code named first, with nothing sent; without an HSN, only `POST`;
  - the heading refused: the product exists, the toast gives the reason, and the dialog is on the product with its Tax section.
- Walked through in the mock as Admin, on a desktop in light mode and a phone in dark mode: a new product with an HSN, then added.
