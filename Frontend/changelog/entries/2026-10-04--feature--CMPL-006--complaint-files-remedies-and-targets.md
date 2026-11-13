---
date: 2026-10-04
type: feature
title: Complaint files, remedies and targets
dataIds:
  - CMPL-006
  - CMPL-007
  - CMPL-008
  - CMPL-009
  - APPR-001
author: Nakul Srivastava
breaking: false
---

## Before

PR #57 took a complaint from raising to the QC verdict, and stopped there:

- A QC-approved complaint had no way forward. The remedy showed read-only, and nobody could choose one.
- Photos of the defect and the challan had nowhere to go.
- The response and resolution targets could not be seen or changed.
- The list could not be downloaded.
- A lead's or an order's page said nothing about its complaints.

The backend has served all of it since #25 (`backend/docs/api/complaints.md`, handover `complaint-remedies-contract.md`).

## Now

- **Files** on a complaint:
  - Photos show as thumbnails from a ten-minute link, read again before it expires. HEIC and PDF show as files to open.
  - Each file shows its kind (photo, document, challan), size and age.
  - Pick a kind and one or more files. Each is checked first (JPEG, PNG, WebP, HEIC or PDF, up to 10 MB, 10 per complaint), then sent on its own. It shows "Uploading…"; a failure keeps its reason and offers **Try again**. One failure never loses the others.
  - Removing a file asks first.
  - Who may add files follows the backend:
    - a draft or a submitted complaint: whoever may raise complaints;
    - under QC: only QC;
    - after that: nobody.
  - After submit, only whoever added a file may remove it.
  - Without file storage, the card says so and offers no upload.
- **The remedy** (QC, on a QC-approved complaint):
  - **Refund**: the amount, who is paid, optionally through a dealer, and why. Then:
    - It goes to the managers by amount, then Accounts.
    - The card shows each step, who decided, and the payment reference once paid.
    - QC may **withdraw** it while it is open.
    - A refund turned down goes back to QC to choose again, and says so.
  - **Replacement**: a free order for the defective quantity.
  - **No action**: closes the complaint at once.
  - Each choice says what happens next.
- **Refunds in the Approvals inbox:**
  - A "Complaint refund" row, with **Open the complaint**.
  - Managers decide it like an order.
  - Accounts must enter the payment reference to approve. Approving closes the complaint.
- **Complaint targets** (`/complaint-targets`, under Admin; anyone with complaints reads them):
  - Each severity's first-response and resolution target, in working hours or round the clock (e.g. "27 working hours (3 days)").
  - Its start day, and whether it is in force, scheduled or ended. Past targets show on request.
  - Those who may edit masters set a new target from a day. The day can't be in the past, and resolution can't be quicker than the first response. A target can cover every complaint type or one.
  - The target in force ends that day. Complaints already submitted keep theirs.
- **Download Excel** on the complaints list, with the filters on screen.
- **A Complaints card** on a lead's page and on a submitted order's: newest first, with **Raise a complaint** about it. A merged lead takes no new complaints.
- **The history** names the backend's real events: sent for approval, paid, not approved, replacement ordered, withdrawn, file added or removed. "Approved by the manager" now reads `complaint.approved`, the event the backend writes. The mock wrote `complaint.checked`.

States covered:

- skeletons for the targets;
- an empty files card, and an empty targets list;
- an upload failing, or refused for its size or type;
- storage unavailable;
- someone acting first (the dialog closes and the page refreshes);
- a phone and dark mode.

## Discussion

**Decisions:**

- **Uploads go one file at a time,** each with its own Idempotency-Key. A retry is replayed, not stored twice. The backend also answers the same file with the one it already has.
- **The upload's answer is ignored.** It is `Envelope_Any_`, so no shape is promised; the complaint is read again for its files.
- **`apiRequest` now sends `FormData`** without a JSON content type, so the browser sets the multipart boundary. Files are logged by name and size only.
- **A refund's approval uses the order's approval view.** `OrderApproval`'s step list became `ApprovalChain`, since a refund carries the same `approvalBlockSchema`.
- **The thumbnails use `<img>`, not `next/image`.** The links are signed for ten minutes, and `next/image` would cache them past that.
- **Complaint types move to the admin masters PR,** with the other lookups.
- **A refund's ladder** follows the "complaint" limits already on the Approval limits screen (#46).

**The mock:**

- **The refund's asker.** Every mock role signs in as one user, so the queue names the seeded QC officer as whoever asked for the refund. Otherwise the deciding manager would be refused as approving their own request.
- **A replacement** names an existing order. The backend raises a new, free one.

**Testing:**

- **jsdom can't stream a `File` through `fetch`:** the request body never ends. So unit tests check the upload's multipart headers and its refusals. The mock's own checks on the file were walked through in Chromium.

## Files changed

- `src/lib/api/client.ts`: `FormData` bodies, sent raw and logged by field.
- `src/features/complaints/api/`:
  - `complaints.schemas.ts`: the remedy, withdraw, attachment, link and target contracts.
  - `complaints.api.ts`, `complaints.queries.ts`, `complaints.mutations.ts`: remedy, withdraw, upload, link, remove, export and targets.
  - `complaints-remedy.test.ts`: the API tests.
- `src/features/complaints/components/`:
  - `remedy-card.tsx`: the remedy, choose and withdraw.
  - `attachments-card.tsx`: files.
  - `complaint-targets.tsx`: the targets screen.
  - `related-complaints.tsx`: a lead's and an order's card.
  - `complaint-dialog-parts.tsx`: `Refusal` and `useCloseLater`, moved out of `complaint-actions.tsx`.
  - `complaint-detail.tsx`: the new cards.
  - `complaints-list.tsx`: Download Excel.
  - `complaints-remedy-ui.test.tsx`: the UI tests.
- `src/features/complaints/lib/complaint-labels.ts`: the file refusals and the remedy history lines.
- `src/features/approvals/`: refunds in the inbox and the decision dialog (payment reference), the doc type, and refreshing the complaint after a decision.
- `src/features/orders/components/order-approval.tsx`: `ApprovalChain`.
- `src/features/orders/components/order-detail.tsx`, `src/features/leads/components/lead-detail.tsx`: the Complaints card.
- `src/app/(app)/complaint-targets/`: the route.
- `src/components/layout/navigation.ts`: Complaint targets, under Admin.
- `src/mocks/`:
  - `handlers/complaints.ts`: remedy, withdraw, a refund's steps, files, export and targets.
  - `handlers/approvals.ts`: deciding a refund's step.
  - `data/approvals.ts`: `refundManagersFor`.
  - `data/complaints.ts`: the seeded targets.
  - `db.ts`: files and targets.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: CMPL-006…009 in progress.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/complaints/`: the records.

## Tests

**`src/features/complaints/api/complaints-remedy.test.ts`:**

- `[CMPL-007]`:
  - a refund goes up the managers, then Accounts' payment reference closes it, and the history shows it;
  - a refund turned down returns to QC;
  - a refund without an amount is refused, and so is anyone but QC;
  - a replacement, withdraw, then no action.
- `[CMPL-006]`: the upload is multipart with the Idempotency-Key; a refusal names its code; a file's link, and removing it.
- `[CMPL-009]`: a dated workbook.
- `[CMPL-008]`: a new target ends the one in force that day; a past day is refused; so is someone who may not edit masters.

**`src/features/complaints/components/complaints-remedy-ui.test.tsx`:**

- the remedy dialog names its mistakes, then sends the refund and shows its steps;
- no action says it closes;
- nobody but QC is offered the remedy;
- a refund in Accounts' inbox needs the payment reference;
- files: the list, removing one, a file over 10 MB refused before sending, and storage unavailable;
- targets: read-only for an officer; set by Admin, refusing a resolution quicker than the response;
- a lead's complaints and "Raise a complaint"; hidden from Dispatch.

**By hand, in Chromium on the mock backend:**

1. QC added a photo to a complaint under QC.
2. QC chose a ₹1,500 refund, trying the empty form first.
3. The District Manager approved it in the inbox.
4. Accounts approved it with the payment reference.
5. The complaint closed, showing the reference.

The targets were checked as Admin on a desktop and on a phone in dark mode. axe found nothing on any of these screens, after the targets' severity cards became level-2 headings.
