---
date: 2026-10-17
type: feature
title: "Import polish: the template, upload errors on their fields, and Import
  from Excel beside New price list"
dataIds:
  - MSTR-013
  - MSTR-007
author: Nakul Srivastava
breaking: false
---

## Before

- **No template.** The backend serves a blank file for each import (`GET /imports/template`), but the import dialog had no link to it. Someone without a sheet in the right layout had nothing to start from.
- **Upload errors as one line.** A wrong sheet, a column-names row past the end, or a file with a header and no rows came back as a message at the top of the dialog, not on the control to fix.
- **Price-list import only inside a draft.** To import a price list, Admin-Sales had to start a blank draft, open it, then find **Import from Excel** there. On staging this read as "the import is missing" from the price lists.

## Now

- **Download the template** in every import's first step (rates, partners, order and quotation lines). It saves as `price-list-template.xlsx`, `partner-import-template.xlsx` or `order-lines-template.xlsx`, since the browser can't read the server's file name. It shows working, then done or failed.
- **Upload errors on their fields** (`fields.file`, `fields.sheet`, `fields.header_row`):
  - an unreadable file, one with too many rows, or a header with no rows under it: under the file picker;
  - an unknown sheet: under **Sheet**;
  - a column-names row past the end: under **Column names on row**, marked invalid and described by its error.
- **Import from Excel beside New price list**, for `pricing.edit`:
  - it opens the new-list form titled "Import a price list from Excel", with **Next: choose the file**;
  - the new draft opens with its import already open (`?import=rates` in the URL, cleared when the import closes);
  - closing without importing keeps the draft, and a note says so: "The draft is kept, with no rates yet."
- Walked through in the mock as Admin on a desktop in light mode and a phone in dark mode. axe found nothing, apart from the Download button's hidden "Downloaded" label caught mid-fade on one run.

## Discussion

- **A draft first, then the file.** The backend imports rates into an existing draft (`target_id`), so the shortcut creates the draft and then opens its import, rather than a new upload-first flow. Cancelling the import leaves an empty draft rather than deleting it: nothing here deletes a price list, and the note tells the user it is there.
- **The URL opens the import**, so a reload on the draft reopens it, and the in-page **Import from Excel** keeps working as before.
- **No backend change.** `backend/docs/api/imports.md` already documents the template and the upload's field errors.

## Files changed

- `src/features/imports/api/imports.api.ts` — `downloadImportTemplate` and the template file names.
- `src/features/imports/lib/import-refusals.ts` — `upload` (file, sheet, header row) on the refusal.
- `src/features/imports/components/import-dialog.tsx` — the template button, the file error under the picker, and the sheet and header-row errors on their controls.
- `src/features/products/components/price-lists-panel.tsx` — **Import from Excel** beside **New price list**; the form's import mode.
- `src/features/products/components/price-list-sheet.tsx` — opens the import from `?import=rates`; the "kept" note.
- `src/mocks/handlers/imports.ts` — the template endpoint, and upload refusals on their fields.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — MSTR-013.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/imports/` — records and screens.

## Tests

- `src/features/imports/api/imports.test.ts`, `[MSTR-013]`: the template under its own name, and refused without permission; an unknown sheet, a far header row and a header-only file each refused on their own field.
- `src/features/products/components/products-ui.test.tsx`, `[MSTR-013]`: **Import from Excel** beside **New price list** lands on the draft with `?import=rates`; the import opens on arrival, the template downloads, a header-only file is named under the picker, and closing says the draft is kept.
