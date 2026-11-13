---
date: 2026-10-15
type: feature
title: "Dealer applications: start one, fill it in, and decide"
dataIds:
  - CHNL-007
author: Nakul Srivastava
breaking: false
---

## Before

The backend recruits dealers (FS-053, `dealer-recruitment-and-small-changes.md`, `docs/api/dealer-applications.md`):

- staff start an application and send the applicant a link (`apply_url`, shown once);
- the applicant fills in the firm's tax, address and bank details and uploads documents;
- a State Manager or above, never whoever started it, approves it, which makes the dealer and its login.

The frontend only had what PR #132 added: winning a dealership lead showed the link it started. Nothing listed applications, filled them in or decided them. The mock's link went nowhere.

## Now

- **Channel partners → Dealer applications** (`/partners/applications`), with tabs on the partners pages:
  - for staff who see partners;
  - newest first, filtered by status and a search on firm, contact or mobile, both kept in the URL.
- **Start an application:**
  - asks for the firm, the contact, the mobile (it becomes the dealer's login) and the area;
  - then shows the link once, with Copy, Share on WhatsApp and "Open the application";
  - a mobile that already signs someone in (`mobile_in_use`), or one with an open application (`application_open`), is refused on the mobile field.
- **An application's page** shows:
  - its status, and what is still needed to submit (`missing`): fields, and the GST certificate, PAN card and cancelled cheque, in words;
  - when the link expires, the manager's remark on a returned one, the reason on a rejected or withdrawn one, and a link to the dealer once approved;
  - the GST record's name, and a warning when the GSTIN's state isn't the area's;
  - the firm, tax, address and bank fields (the account number masked unless the reader may see it), and who started and decided it.
- **What staff can do there** (from `can`):
  - **Edit details** fills or corrects every field. Only the changes are sent. The PAN is checked against the GSTIN. Under a GSTIN, the GST record offers its names (#132's check);
  - **Documents** attach, open and are removed as on any record (`record_type: dealer_application`);
  - **Submit for them**, which is disabled while something is missing;
  - **New link**: the old link stops, and the new one shows once;
  - **Withdraw**, with a reason.
- **Decide**, for a State Manager or above who didn't start it:
  - approve, under a distributor (optional) and with a partner code (optional; empty means the next one);
  - return, saying what to fix;
  - or reject, saying why.

  Approving refreshes the partners, and the page links the new dealer.

- **Shared code:**
  - the link panel (`ApplyLink`) is shared with the lead-win dialog;
  - the fields editor is written to serve the applicant's own page next (plan item 19b);
  - the Documents card takes an `emptyHint`, so an application asks for its own documents.
- **The mock** follows `dealer_applications.py`:
  - `missing` from the fields and documents;
  - `can`, and who may decide;
  - the mobile, PAN, GSTIN, IFSC and pincode checks;
  - approval adds the dealer with the next `DLR-GJ-` code.

  Winning a dealership lead now starts a real mock application, so its link and page work.

- Checked on a desktop in light mode and a phone in dark mode: the list, starting one, a draft and its edit dialog, deciding and approved. axe found nothing after the approved notice's link was underlined.

## Discussion

- **Stacked on #132** (dealership enquiries and the GSTIN check), whose pieces this reuses. Merge #132 first, then retarget this to `integration`.
- **The applicant's own page** (`/dealer-apply/<token>`: verify by WhatsApp code, fill in, upload, submit) is plan item 19b, next.
- **A dealer application isn't reachable from its lead yet.** The lead keeps `lead_id` on the application, not the other way round, and the list has no `lead_id` filter.
- **The document types offered** come from `GET /documents/types` for every record. BE-025 asks for them by record type.
- **Not yet checked on staging.**

## Files changed

- `src/features/dealer-applications/api/*`: new; the schemas, the eight calls, queries and mutations.
- `src/features/dealer-applications/components/*`: new; the list, start, detail, actions (submit, new link, withdraw, decide), the edit form and fields, the link panel, and refusals in words.
- `src/features/dealer-applications/lib/dealer-application-labels.ts`: new; statuses, firm types, decisions and what `missing` names.
- `src/app/(app)/partners/applications/page.tsx`, `[applicationId]/page.tsx`: new routes.
- `src/app/(app)/partners/page.tsx`, `src/features/partners/components/partners-tabs.tsx`: the tabs.
- `src/features/leads/components/dealer-application-started.tsx`: uses the shared link panel.
- `src/features/documents/components/record-documents.tsx`: `emptyHint`.
- `src/mocks/handlers/dealer-applications.ts`, `src/mocks/data/dealer-applications.ts`, `src/mocks/db.ts`, `src/mocks/data/reference.ts`, `src/mocks/handlers/index.ts`: the mock.
- `src/mocks/handlers/documents.ts`, `partners.ts`, `leads.ts`: documents on an application, the GSTIN check shared, and a real application on a dealership win.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: CHNL-007.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/partners/dealer-app*`: records and screens.

## Tests

- `src/features/dealer-applications/components/dealer-applications.test.tsx`:
  - through the API: starting one with its link, then the link gone on a read, and the mobile refusals; nothing submitted while something is missing, and the PAN checked against the GSTIN; an employee can't decide, a State Manager must give a reason to return, and approving adds the dealer; the status filter;
  - the list, and starting one with the link to send;
  - a draft's missing fields and documents, and staff filling them in (a wrong pincode said in words);
  - a State Manager rejecting without a reason, then approving, and the dealer linked;
  - a returned one's remark, and withdrawing it.
- `src/features/leads/components/lead-stage.test.tsx`: the dealership win's link is now a real mock application.
- Walked through in the mock: desktop light and phone dark.
