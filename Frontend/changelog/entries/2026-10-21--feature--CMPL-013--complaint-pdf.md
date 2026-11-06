---
date: 2026-10-21
type: feature
title: Download a complaint as PDF
dataIds:
  - CMPL-013
author: Nakul Srivastava
breaking: false
---

## Before

After the QC verdict a complaint's files are locked, and the 18 Oct walk asked whether that was meant (F-12). A complaint also had no printable copy to send or file, unlike a quotation or a sales order.

## Now

The user decided on 20 Oct: files stay locked after the QC verdict, and a complaint gets a **Download PDF** like a quotation or an order.

- **Download PDF** sits by the complaint's actions once it is submitted.
  - It asks for a ten-minute link on each click and opens it in a new tab, with the same button as quotations and orders (`PdfLinkButton`).
  - While the PDF renders it says "Preparing PDF…"; a refusal says why.
- **The backend doesn't serve it yet.** BE-031 asks for it in the order's shape:
  - `pdf_state` on the complaint (`none`, `pending`, `ready`, `failed`);
  - `GET /complaints/{id}/pdf` returning the link.
- **Nothing changes on staging until then.** The button shows only when `pdf_state` arrives.

**Mock**

- `pdf_state` is `none` for a draft and `ready` once submitted.
- The link names the file after the complaint number; a draft's link is a 404.

Walked as Admin on a desktop in light mode and a touch phone in dark mode, on a closed complaint. Axe found nothing, with no sideways scroll.

## Discussion

- **Built ahead of the backend, on purpose.** The contract mirrors the order's PDF, which the backend already serves, so the shape is unlikely to move. Plan.md §9.2 lists it as mocked until BE-031 is done.
- **What the PDF contains is the backend's call.** BE-031 suggests:
  - the number, status and severity;
  - the parties;
  - the lines;
  - the check, the QC verdict and the remedy;
  - the history.

## Files changed

- `src/features/complaints/api/complaints.schemas.ts`: `pdf_state` on the complaint, `pdfState` on the screen.
- `src/features/complaints/api/complaints.api.ts`: `getComplaintPdf`.
- `src/features/complaints/components/complaint-detail.tsx`: **Download PDF**.
- Mock: `src/mocks/handlers/complaints.ts`, the state and the link.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: CMPL-013.
- `docs/Backend-Tasks.md`: BE-031.
- Records: `Docs/Plan.md` (§9.2), `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/complaints/complaint-pdf-*`.

## Tests

`src/features/complaints/components/complaint-pdf.test.tsx`, 4 tests:

- `[CMPL-013] A complaint's PDF (contract)`: none for a draft and a 404; a link once submitted.
- `[CMPL-013] Download PDF on the complaint`:
  - a closed complaint's PDF opens in a new tab, with no opener;
  - no button on a draft;
  - no button while the backend doesn't send `pdf_state`.

To check by hand in the mock, open any closed complaint and select **Download PDF**.
