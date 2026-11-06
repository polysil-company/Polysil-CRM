---
date: 2026-10-13
type: feature
title: Documents on leads, quotations, orders and dispatches
dataIds:
  - DOC-001
  - DOC-002
  - DOC-003
author: Nakul Srivastava
breaking: false
---

## Before

The client handles purchase orders, payment slips, invoices and transport receipts outside the app. The backend now keeps them on the record they belong to (FS-050, `backend/docs/api/documents.md`, handover `documents-and-replacement-chain.md`). The frontend had no screen for it, so a bill or PO PDF could not be attached anywhere.

## Now

- **A Documents card** on the lead, quotation and order pages, and a Documents section on each dispatch on the order page.
  - The list is newest first. Each row shows the document's name (or its type), the type, the file name and size, and who added it and when.
  - **Open** uses the backend's ten-minute link, which is renewed before it runs out and is never fetched with the bearer token. A HEIC photo, which browsers can't show, is offered as **Download** instead.
- **On the lead**, the card shows everything on the lead and on what came from it: its quotations, their orders, those orders' dispatches, and leads merged into it. Each row names its record, such as "Quotation QT/GJ/…" or "Order SO/GJ/…", linked where the record has a page.
- **Attach a file** (DOC-002).
  - **The form.** Pick what it is from the backend's types, then give a name for "Other" (a note otherwise, up to 80 characters), then choose one file.
  - **Checks before sending.** A missing type or file, a missing name for "Other", a file over 10 MB, and a file that isn't JPEG, PNG, WebP, HEIC or PDF are each named first.
  - **Refusals.** Each backend refusal has its sentence: 413; `attachment_type`; `too_many_documents` at 50; `record_closed` on a merged lead or a voided dispatch; `storage_unavailable`; 403; 404.
  - **The same file again.** It answers with the one already there, and the toast says so.
- **Remove** (DOC-003) asks first. It's offered to whoever added the document, and to staff who may add to the record it sits on (on a lead, the lead's own documents).
- **Who adds**, from the handover:
  - Leads: whoever edits them, a dealer on their own leads.
  - Quotations: staff who edit quotations.
  - Orders: whoever edits them.
  - Dispatches: Dispatch, or the order's editor.
  - A merged lead and a voided dispatch take none.
- Checked on a phone in dark mode and a desktop in light mode. axe found nothing.

## Discussion

- **One component, two shapes.** It's a card on a page. On the order page each dispatch gets a section, named after its number ("Documents on D/SO/…") so the lists and buttons on that page stay distinct.
- **Links are fetched one per document and renewed every nine minutes**, as the complaint and subsidy files do. A list holds 50 documents at most.
- **The type picker shows every type the backend lists.** That includes the five a dealer application uses (GST certificate, PAN card…). BE-025 asks for a `record_type` filter rather than the frontend hard-coding which types to hide.
- **Payments aren't built here.** The backend takes documents on payments (Accounts). There is no payments screen yet, so none is offered.
- **Stacked on #111** for its upload plumbing: the multipart reader in the mock, multipart in jsdom tests, and `formatFileSize`.

## Files changed

- `src/features/documents/` — new: the contract, calls, queries, mutations and tests; refusal messages; the `RecordDocuments` card with its attach and remove dialogs, and its tests.
- `src/features/leads/components/lead-detail.tsx` — the lead's documents card.
- `src/features/quotations/components/quotation-detail.tsx` — the quotation's documents card.
- `src/features/orders/components/order-detail.tsx`, `order-dispatches.tsx` — the order's card, and a section per dispatch.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — the DOC domain; DOC-001 to DOC-003.
- `src/mocks/data/documents.ts`, `src/mocks/handlers/documents.ts` — new: the types, a seeded story, and the endpoints with the backend's rules. Also `db.ts`, `handlers/index.ts` and `data/reference.ts`.
- `../docs/Backend-Tasks.md` — BE-025.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/documents/` — records and screens.

## Tests

- `src/features/documents/api/documents.test.ts`:
  - `[DOC-001]`: types; one record's list; a lead's whole story with labels; the link; 404.
  - `[DOC-002]`: attach, and the same file again; Other unnamed; a wrong type; over 10 MB; quotations staff only; a merged lead; a voided dispatch.
  - `[DOC-003]`: remove; a partner refused someone else's.
- `src/features/documents/components/record-documents.test.tsx`:
  - The order's list, with Open and Download.
  - The lead's story, with record links.
  - Nothing to add on a closed record.
  - Attach, with its missing fields, the name for Other, and success.
  - A bad file refused before sending.
  - Remove.
- Walked through in the mock:
  - On the desktop in light mode: the lead, the order (with a dispatch's section) and the quotation; attach and remove on the order.
  - On a phone in dark mode: the lead's card and the attach dialog.
  - As a dealer on its lead: Attach is offered, but not Remove on Polysil's files.
