---
date: 2026-10-15
type: feature
title: "Reopen a closed subsidy file, and the document checklist"
dataIds:
  - SUBS-015
  - SUBS-007
author: Nakul Srivastava
breaking: false
---

## Before

A subsidy application closes by itself once every stage-16 amount has its stage-17 date. After that it takes no more entries. When a date or an amount had been entered wrong, nobody could correct it from the screen.

The backend added `POST /subsidy-applications/{id}/reopen` (`subsidy-completion.md` §4) and `GET /subsidy-document-types`, the checklist every application is given. The frontend used neither.

## Now

- **Reopen** shows on a closed ("Fully paid") file, only for those with `subsidy.approve`: Admin Sales and the MD.
  - The closed file's note tells them they can reopen it to correct an entry, and that it closes again when the payment entries are complete.
  - The dialog asks why (1 to 500 characters) and says that the file's owner and the lead's owner are told.
  - Afterwards the file is open, with its stages and figures as they were, and **Record stage** and **Cancel** are back.
- **It closes again** only when an entry writes a stage-16 amount or a stage-17 date, as the backend checks.
- **Refusals:**
  - no reason: on the field;
  - `409 commission_settled`: "The dealer's commission is settled". The file stays closed;
  - `409 application_not_closed`: the dialog closes, a toast says why, and the file refreshes;
  - `403`: "Not yours to reopen".
- **Subsidy masters → Documents** lists the checklist from `GET /subsidy-document-types`.
  - Each item is numbered, with its code; an item no longer asked for is marked.
  - It is read only and the same for every scheme.
- **The mock:**
  - It seeds one closed file through every stage.
  - Reopen needs `subsidy.approve`.
  - A file closes again only on an entry that writes a payment field, so reopening and then opening the file no longer closes it.
  - It serves the checklist, and records `subsidy.reopened` on the lead's history.
- Checked on a desktop in light mode and a phone in dark mode: the closed file, the dialog, the reopened file and the checklist. axe found nothing.

## Discussion

- **Why a Documents tab:** each application's checklist already names its items, so `GET /subsidy-document-types` adds nothing there. The tab lets an administrator read the list without opening an application. If the client wants the list editable, that needs a backend endpoint.
- **The commission rule can't be shown in the mock,** which has no dealer commissions; a test stands in for it.
- **Not yet checked on staging.**

## Files changed

- `src/features/subsidy/api/subsidy-applications.schemas.ts`, `.api.ts`, `.queries.ts`, `.mutations.ts`: `reopenApplication`, `listDocumentTypes` and their query and mutation.
- `src/features/subsidy/components/application-actions.tsx`: the Reopen button and dialog.
- `src/features/subsidy/components/application-detail.tsx`: `subsidy.approve`, and the closed note's hint.
- `src/features/subsidy/components/document-checklist-panel.tsx`: new, the checklist.
- `src/features/subsidy/components/subsidy-masters.tsx`: the Documents tab.
- `src/mocks/handlers/subsidy-applications.ts`: the reopen and checklist routes, a closed seeded file, and closing only on a payment entry.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SUBS-015, and `GET /subsidy-document-types` under SUBS-007.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/subsidy/`: records and screens.

## Tests

- `src/features/subsidy/components/subsidy-reopen.test.tsx`:
  - a closed file reopened stays open until a payment entry closes it again;
  - a missing reason, an open file and someone without `subsidy.approve` refused;
  - the checklist read;
  - on the page: the hint, the empty reason, the reopen and the buttons back;
  - no Reopen for a District Manager;
  - a settled commission explained in the dialog;
  - a file no longer closed closes the dialog;
  - the masters checklist, with an item no longer asked for.
- Walked through in the mock: desktop light and phone dark.
