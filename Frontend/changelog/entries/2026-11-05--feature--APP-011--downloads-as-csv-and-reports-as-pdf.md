---
date: 2026-11-05
type: feature
title: Downloads as CSV, and reports as PDF
dataIds:
  - APP-011
author: Claude
breaking: false
---

## Before

- The backend's FS-077 gave every download a `format`:
  - a list comes as Excel (the default) or CSV;
  - a report also comes as PDF;
  - a list asked for PDF answers `422 format_not_available`;
  - a PDF maker at its limit answers `503 busy`.
- Every download button in the app asked for Excel only.

## Now

- **Every Download Excel button** has a small **Other formats** menu beside it with **Download CSV**:
  - leads, quotations, sales orders and the Accounts queue;
  - tasks, complaints, users, channel partners;
  - dealer commission, marketing orders, subsidy applications, and the three subsidy reports.
- **Reports** offer **Download CSV** and **Download PDF**.
- **File names:** each file is saved under the backend's name. Without one, the name ends in the format's extension (`orders.csv`).
- **Refusals:** more than 5,000 rows says to narrow the filters, as before. A busy PDF maker says to try again in a moment.
- **The mock** answers `format=csv` with a comma-separated file and `format=pdf` with a stand-in PDF, through the one `mockWorkbook` every export uses. The three exports that built their own file (complaints, marketing orders, tasks) now use it too.

## Discussion

- **A menu beside the button, not a new button per format.** "Download Excel" stays where people know it, and the other formats sit one click away without crowding a toolbar on a phone.
- **Every export call takes a `format`, Excel by default,** and every button passes the format chosen. The query now always says `format=xlsx` for Excel, which is the backend's default anyway.
- **PDF only on reports**, as the backend allows. Lists don't offer it, so nobody meets `format_not_available`.

## Files changed

- `src/components/patterns/download-excel-button.tsx`: the Other formats menu, the format passed to `download`, and the busy message.
- `src/lib/api/client.ts`: `ExportFormat`.
- `src/features/*/api/*.api.ts`: a `format` on every export call (fourteen).
- `src/features/*/components/*.tsx`: every button passes the format; reports offer PDF.
- `src/mocks/handlers/shared.ts` and the export handlers: CSV and PDF.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: APP-011.
- `Docs/plan-13oct-2026.md`: record.

## Tests

- **`[APP-011] DownloadExcelButton`:**
  - Excel, then CSV from Other formats, saved as `.csv`;
  - PDF offered where the caller allows it;
  - the mock answers CSV with a `.csv` file.
- **The feature tests with a download pass:** 715 of 716 in the batch. The one failure was `lead-assign`, under heavy load; it passes on its own (6 of 6) and has nothing to do with downloads.
