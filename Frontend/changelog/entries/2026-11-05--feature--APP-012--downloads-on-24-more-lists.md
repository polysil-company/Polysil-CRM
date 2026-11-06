---
date: 2026-11-05
type: feature
title: Downloads on 24 more lists
dataIds:
  - APP-012
author: Claude
breaking: false
---

## Before

- The backend's FS-081 added `GET <list>/export` beside every list that lacked one: 24 lists, Excel or CSV, with the list's own filters and every page. More than 5,000 rows is `422 export_too_large`.
- In the app, only leads, quotations, orders, tasks, complaints, users, partners, commissions, marketing orders and subsidy applications had a download.

## Now

- **Download Excel**, with **Other formats → Download CSV** beside it, on:
  - **Products:** the catalogue, tax rates, price lists, one list's rate sheet, and seller GSTINs;
  - **Stock:** the stock list, the stock ledger, and warehouses (switched-off ones too);
  - **Sales and accounts:** customers, receipts, ratings, and dealer applications;
  - **Masters:** offices, territories, the year's holidays, warranty periods, and subsidy schemes;
  - **Schemes and rewards:** schemes, scheme credits, a points history, gifts, the gift desk's requests, and earning rules;
  - **Campaigns.**
- **Each download sends the filters on screen**, never a page or cursor, so the file holds what the list shows across every page.
- **The mock** answers all 24 with the backend's column headings and one sample row, as Excel or CSV. Its handlers come first, so `/products/export` isn't read as a product id.

## Discussion

- **One call per list, beside the list's own call,** reusing its filter mapping, so the file and the screen can't drift apart.
- **Where the button sits:** in the toolbar beside the list's main action, or in the card's header. On the dealer applications list it sits with the filters, leaving the header row to the blank-form menu that item 43 adds.
- **Dealer applications:** the download also sends the dealer or distributor filter (`partner_type`, from PR #228), so the file matches the list. Added when this pull request was brought up to date with `integration`, 6 Nov.
- **The points history** downloads the ledger the card shows: the user's own, or the partner's or person's being looked at.

## Files changed

- `src/features/*/api/*.api.ts`: 24 export calls (products, tax rates, price lists and items, seller GSTINs, customers, warehouses, stock, movements, payments, warranty terms, offices, territories, holidays, dealer applications, campaigns, schemes, entitlements, subsidy schemes, ratings, ledger, gifts, redemptions, rules).
- `src/features/*/components/*.tsx`: the button on 23 screens (the points card covers the ledger).
- `src/mocks/handlers/list-exports.ts`, `index.ts`: the 24 mock exports, registered first.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: APP-012.
- `Docs/Tested-Features.md`, `Docs/Plan.md` §9.1, `Docs/plan-13oct-2026.md`: records.

## Tests

- **`[APP-012] Downloads on 24 more lists`** (`src/mocks/handlers/list-exports.test.ts`):
  - all 24 calls download Excel and CSV under the backend's file name, with the first column heading;
  - the stock export sends only its filters and `format`;
  - the dealer applications download sends the dealer or distributor filter;
  - `export_too_large` is refused.
- **`[APP-012] Downloads on the stock screens`:** the stock list saves Excel; the ledger saves CSV from Other formats.
