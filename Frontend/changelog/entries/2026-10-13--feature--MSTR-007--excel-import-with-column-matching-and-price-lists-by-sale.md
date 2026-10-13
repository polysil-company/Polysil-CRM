---
date: 2026-10-13
type: feature
title: Excel import with column matching, and price lists by sale type
dataIds:
  - MSTR-007
  - MSTR-008
author: Nakul Srivastava
breaking: false
---

## Before

The backend's Excel import (FS-062, `backend/docs/api/imports.md`) and price lists by sale type (FS-061) had reached `integration` with no screens. A draft price list's rates were typed in one by one. A quotation's or order's items were added row by row. A price list had no sale type, and the builders priced every line from the general list whatever the quotation's sale type.

## Now

- **One import dialog for every kind (MSTR-007).** Four steps, shown as a trail: **Upload** (`.xlsx` or `.csv`, up to 10 MB, checked before it is sent), **Match columns**, **Review**, **Done**.
  - Match: every column in the file is listed with its five sample values and a picker. The pick is "Skip this column" or one of the import's fields, with "(required)" marked and each field's help line. The backend's suggested match is filled in. "Still to match: Rate" names what is missing. A workbook's sheet is picked from a list, and the row that holds the column names can be changed and read again. Both are a new upload of the same file.
  - Review: "N ready" and "N with errors" badges. A table of the bad rows gives row number, column and reason. The first 20 good rows show as they will be saved. Column warnings come from the backend.
  - Two ways out: **Import good rows only**, or **Import N rates**, which is all or nothing. Going **Back to matching** keeps the upload.
  - A rejected mapping is shown on its field. If rows changed since the check, the commit refusal names them. A published list, a finished import, a file too big or unreadable, and no permission each get one plain sentence. An upload closed without committing is discarded.
  - Keyboard: the long tables scroll inside regions that take focus.
- **Rates into a draft price list.** **Import from Excel** on a draft's sheet. Pick **Replace** (the file becomes the whole list) or **Merge** (rates not in the file stay). Done says "3 rates written, 2 skipped." and the sheet reloads. The button is off while typed rates are unsaved, so an import never lands on top of unsaved edits.
- **Items into a quotation or order.** **Import from Excel** on the Items card checks the file's lines and adds the good ones with "Add to quotation: the 2 good items" (or "to order"). Each added line takes its product, quantity and up to three discounts, then prices live like any other line. An untouched empty row gives way to the imported lines.
- **Price lists by sale type (MSTR-008).**
  - A list is for one sale type (Commercial, Industrial or Subsidy) or for all.
  - The new-list form asks for it. The list row and the sheet header show it.
  - A **Sale type** filter on Price lists has an "All sale types (general)" choice.
  - A copy keeps the sale type.
  - The quotation builder sends the quotation's sale type with every price preview. The order builder sends its order type the same way. A Subsidy quotation is priced from the Subsidy list where one is in force.
- Phone and desktop, light and dark. On a phone the dialog takes the screen's width and scrolls. Every step has its loading state on the button that started it.

## Discussion

- **One dialog, three imports.** The backend serves partners, price-list rates and lines from one set of endpoints. The dialog takes the kind and a noun ("rates", "partners", "items"), so partners (CHNL, next pull request) reuse it unchanged.
- **Lines have no commit.** As the contract says, a `lines` import ends at the check. The good rows go into the builder's form and are saved with the quotation or order, so nothing is written until the person saves.
- **Multipart in tests.** jsdom's `fetch` can't send a `FormData` body to MSW, so `src/test/multipart-fetch.ts` encodes it in tests only. The mock reads multipart itself (`readMultipart`).
- **The mock reads CSV only.** It has no Excel reader, so any `.xlsx` gets a sample workbook for its kind, with a second sheet so the sheet picker shows. The backend reads both.
- **Imported lines name no unit.** The `lines` check returns the product but not its unit, so the quantity box takes its unit from the price preview once it arrives.
- **Fixed on the way:** "Indicative rate" on a priced line sat in a `<dl>` without a term (axe `definition-list`). It now has a visually hidden "Rate status" term.
- **Not checked on staging yet.** The import endpoints are on `integration` (backend). The 🔌 check is in the PR's test plan.

## Files changed

- `src/features/imports/` — new: the contract (`imports.schemas.ts`), calls (`imports.api.ts`), mutations, refusal messages (`lib/import-refusals.ts`), the four-step `ImportDialog`, and API tests.
- `src/features/products/api/` — `sales_type` on price lists, the list filter, and the copy keeps it.
- `src/features/products/components/price-lists-panel.tsx` — the Sale type filter, the form field, and the row label.
- `src/features/products/components/price-list-sheet.tsx` — sale type in the header; **Import from Excel** on a draft.
- `src/features/products/lib/product-labels.ts` — sale type labels.
- `src/features/quotations/` — `sales_type` in price previews; `draftLinesFromImport`; `addLines`; **Import from Excel** on the Items card; the unit from the preview; the `dl` fix.
- `src/features/orders/components/order-builder.tsx` — the order type in price previews; import on the Items card.
- `src/lib/format/number.ts` — `formatFileSize`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — MSTR-007, MSTR-008.
- `src/mocks/` — the import fields, sample workbooks, CSV reader and handlers. Price lists filter by sale type. Shared: `readMultipart`.
- `src/test/multipart-fetch.ts`, `vitest.setup.ts` — multipart bodies in jsdom.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/imports/` — records and screens.

## Tests

- `src/features/imports/api/imports.test.ts` — `[MSTR-007] Excel import — price list rates`: headers and suggestions, every row checked, all-or-nothing, good rows only, a finished import, a mapping refusal on its field, unreadable, too big, a published list, no `pricing.edit`, workbook sheets, discard. `[MSTR-007] … order and quotation lines`: good rows returned, no commit.
- `src/features/products/components/products-ui.test.tsx` — `[MSTR-008] Price lists by sale type` (create with a sale type, filter, label) and `[MSTR-007] Import rates from Excel` (the whole flow through the dialog, a mapping problem on its field and a discard on close, no import on a published list).
- `src/features/quotations/components/quotation-builder.test.tsx` — `[MSTR-007] Items from Excel`.
- `src/features/quotations/lib/builder-lines.test.ts` — the sale type in previews; `draftLinesFromImport`.
- `src/lib/format/format.test.ts` — `formatFileSize`.
- Walked through in the mock: new list with a sale type, filter, a rate import at desktop light and phone dark, items into a quotation. axe found nothing on the dialog's four steps.
