---
date: 2026-10-02
type: fix
title: "Approval limits read the backend's refund limits instead of failing"
dataIds:
  - APPR-002
author: Nakul Srivastava
breaking: false
---

## Before

On the dev API, Admin → Approval limits showed "We received data we couldn't read" (REF APPR-002) for everyone.

Complaint remedies (backend #38, FS-015b, migration 026) added a third kind of approval limit: `doc_type: "complaint"`, the refund ladder. A refund is approved in rupees by the order's three managers, then paid by Accounts. The seeded limits are ₹25,000 for District, ₹1,00,000 for State, and no limit for Regional.

The screen accepted only `sales_order` and `quotation`, so the first refund row made the whole answer a contract violation.

## Now

- **The page shows three ladders:** Order value, Discount on a quotation, and the new **Refund on a complaint** (rupees; District, State and Regional managers, then Accounts).
- **Administrators can change refund limits** with the same dialog and the same rules: each level above the one below, "No limit" only at the top. For example: "State Manager's refund limit: refunds up to this amount are approved at this level, then go to Accounts."
- **Unknown kinds no longer break the page.** A limit row for a document the screen doesn't know yet is left out instead of failing it, so the backend can add one without taking the page down again.
- **The mock backend** seeds the backend's refund limits and accepts changes to them.

## Discussion

- **Refund requests don't show in the Approvals inbox yet.** The inbox reads its rows one at a time and leaves out a row it doesn't know, so it never failed. But there is no complaint screen to open yet: `TODO(CMPL-001)` adds refund steps with the complaint screens.
- **No backend change is needed.** The backend's contract documents `complaint` in `ThresholdPut.doc_type` (`backend/docs/api/approvals.md`). Only the frontend lagged behind.

## Files changed

- `src/features/approvals/api/approvals.schemas.ts`: `THRESHOLD_DOC_TYPES` with `complaint`; rows of unknown documents left out; `Threshold` as an explicit type.
- `src/features/approvals/lib/approval-limits.ts`: the refund ladder uses the order's managers; `limitUnit`.
- `src/features/approvals/components/approval-limits.tsx`: the "Refund on a complaint" ladder.
- `src/features/approvals/components/approval-limit-dialog.tsx`: refund wording, and the unit from the document.
- `src/mocks/data/approvals.ts`, `src/mocks/handlers/approvals.ts`: the refund limits, and changes to them.
- `Docs/Tested-Features.md`.

## Tests

- **`src/features/approvals/api/approval-limits.test.ts`** `[APPR-002]`
  - Reads the refund limits.
  - Leaves out an unknown document's rows. This test reproduces the reported error on the old schema.
  - Changes a refund limit.
- **`src/features/approvals/components/approval-limits.test.tsx`** `[APPR-002]`: the three ladders, refunds included.
