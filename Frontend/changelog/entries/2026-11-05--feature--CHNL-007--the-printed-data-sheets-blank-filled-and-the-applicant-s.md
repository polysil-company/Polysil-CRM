---
date: 2026-11-05
type: feature
title: "The printed data sheets: blank, filled and the applicant's"
dataIds:
  - CHNL-007
  - CHNL-008
author: Claude
breaking: false
---

## Before

- FS-071 gave the backend three printed versions of the application's data sheet, as the client's paper form:
  - **blank**, to fill in by hand (`GET /dealer-applications/form.pdf?partner_type=`);
  - **filled from an application**, for staff (`GET /dealer-applications/{id}/pdf`, with the bank account masked for everyone);
  - **the applicant's own as filled so far**, to print and sign (`GET /public/dealer-apply/{token}/pdf`, with the applicant's session).
- The frontend offered none of them.

## Now

- **The applications list** has a **Blank form** menu: "For a new dealer" or "For a new distributor" saves that type's blank sheet.
- **An application's page** has **Download PDF**, beside its other actions, for the sheet filled from the application.
- **The applicant's page** has **Download to print and sign**, above Submit. It says the sheet holds what is saved so far, so unsaved typing should be saved first.
- **Each is saved under the backend's own file name.**
- **When the backend's PDF maker is at its limit** (`503 busy`), the toast says "The PDF maker is busy. Other PDFs are being made. Try again in a moment." `pdf_unavailable` says PDFs can't be made just now. Anything else shows its own reason.
- **A new pattern, `DownloadFileButton`,** for any file the backend makes when asked. It has its states (Preparing…, Downloaded, Not downloaded), the busy and unavailable messages, and stories. The CSV and PDF downloads (item 46) build on it.

## Discussion

- **The PDFs come back as the file itself, not a link.** They are fetched with the session through the API client and saved, like Download Excel. That way a sheet with someone's details never sits behind a bare URL.
- **The applicant's download carries their session** (`X-Apply-Session`), as every applicant call does. Without one, the backend says to verify the mobile again.
- **Where the buttons sit.** The blank form goes with "Start an application", since both are about a new partner. The filled sheet goes on the application. The applicant's goes by Submit, where they finish.
- **The mock** answers each with a stand-in PDF named as the backend names them. Its blank-form route comes before `/:applicationId`, so `form.pdf` isn't read as an id.

## Files changed

- `src/components/patterns/download-file-button.tsx` (new), with stories: the button and `toastDownloadError`.
- `src/features/dealer-applications/api/dealer-applications.api.ts`, `dealer-apply.api.ts`: the three downloads.
- `src/features/dealer-applications/components/dealer-applications-list.tsx`, `dealer-application-detail.tsx`, `dealer-apply-form.tsx`: Blank form, Download PDF, and Download to print and sign.
- `src/mocks/handlers/dealer-applications.ts`: the three PDFs.
- `Docs/plan-13oct-2026.md`, `Docs/Tested-Features.md`: records.

## Tests

- **`[CHNL-007] The printed sheets (FS-071), through the API`:** the blank form for each type and an application's own, by name. The applicant's only once their mobile is verified (`no_session` before).
- **`[CHNL-007] The printed sheets on the screens`:** Download PDF saves the application's sheet, then a busy PDF maker is said in words; Blank form → "For a new distributor" saves that type's form.
