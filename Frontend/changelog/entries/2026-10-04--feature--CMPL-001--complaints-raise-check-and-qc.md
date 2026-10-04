---
date: 2026-10-04
type: feature
title: "Complaints: raise, check and QC"
dataIds:
  - CMPL-001
  - CMPL-002
  - CMPL-003
  - CMPL-004
  - CMPL-005
author: Nakul Srivastava
breaking: false
---

## Before

Complaints was a "Soon" item in the sidebar. The backend has served complaints since #25: 21 endpoints, documented in `backend/docs/api/complaints.md` and the handovers `complaints-contract.md` and `complaint-remedies-contract.md`. A farmer's report of cracked laterals had no place in the CRM: no number, no check, no QC, and no target to answer by.

## Now

The complaint flow, from raising to the QC verdict.

- **The list** (`/complaints`):
  - Newest first. Each row shows the number, status, severity, a red "Late" when a target was missed, the contact, type, dealer, owner and age.
  - Counts across the top: waiting for a check, with QC, late.
  - Search, plus filters for status (each one explained), severity, type, late only and no owner. All of them are kept in the URL.
  - **Waiting on me**, for managers and QC: what waits for their check or verdict, oldest first.
- **Raise a complaint** (`/complaints/new`):
  - type, severity, what went wrong, the contact and mobile, where it is installed, and the dealer;
  - the challan and supply date, registration and PIMS numbers, and the sample's courier;
  - the products, with supplied and defective quantities: 1 to 20, each once, defective not more than supplied.
  - Every mistake is named on its field at once. It is saved as a draft.
  - Opened as `?lead=` or `?order=`, the complaint is linked to that lead or order.
- **Edit a draft** (`/complaints/{id}/edit`): only what changed is sent. The header and the products go as two separate calls.
- **The complaint** (`/complaints/{id}`):
  - what happened, the contact (tap to call), the dealer, the lead and order (linked), the challan, the owner, and who raised it;
  - the products, with defective quantities in red;
  - the **targets**: first response and resolution, due, met or missed. "No target" is never red.
  - the manager's check and the QC verdict, internal notes included for staff;
  - the remedy, read-only, when there is one;
  - the history, newest first.
  - A returned draft says who returned it and what to fix.
- **Actions** follow the complaint's `can`:
  - **Submit:** numbers the complaint and starts its targets. Without the challan or supply date, it says which one to add. With nothing defective, it says so.
  - **Check** (managers): approve it to QC, optionally changing the severity or setting an owner, or return it to fix. Both need a remark the raiser reads; an internal note is optional.
  - **QC verdict:** approved (a defect) or rejected (no defect), with what QC found and the sample's dates, none after today.
  - **Cancel**, with a reason.
  - **Delete**, for a draft never submitted.
  - If someone acted first, the dialog closes and the page shows the latest.
- **Notifications** about a complaint now open it.

## Discussion

**What comes in the next PR (C2):**

- photos and documents (multipart upload, ten-minute links, HEIC without a preview);
- the remedy: a refund through the Approvals inbox, with a third limits tab; a replacement order; or no action; and withdrawing one;
- the targets and complaint types admin screens;
- the Excel export;
- a lead's and an order's complaints.

Every Data ID is registered (CMPL-001…009).

**Decisions:**

- **`can` decides every button**, not the user's role. The backend works out who may check, which depends on area and role, and who may give the verdict.
- **The form shows all of a product's mistakes at once.** Zod skips an object's refinement while any of its fields fails, so a quantity mistake would otherwise appear only after the product was picked.
- **Managers' mock permissions.** They gained complaints `approve`, as in RBAC.md §6.1 (District and State: CEA). Accounts gained complaints `view`: they see complaints because refunds are paid through them.
- **The mock's targets.** They count plain hours, doubled. The backend counts working hours (Monday to Saturday, 09:30 to 18:30). The screen shows whatever the backend sends.

## Files changed

- `src/features/complaints/api/`: `complaints.schemas.ts` (the whole contract, remedy included), `complaints.api.ts`, `complaints.queries.ts`, `complaints.mutations.ts`, `complaints.test.ts`.
- `src/features/complaints/lib/complaint-labels.ts`: statuses, severities, the backend's refusals in plain words, and the history lines.
- `src/features/complaints/hooks/use-complaint-list-params.ts`: the URL state.
- `src/features/complaints/components/`: `complaints-list.tsx`, `complaint-form.tsx`, `dealer-picker.tsx`, `complaint-detail.tsx`, `complaint-actions.tsx`, `complaint-pages.tsx`, `complaints-ui.test.tsx`.
- `src/app/(app)/complaints/`: the list, new, detail and edit routes.
- `src/components/layout/navigation.ts`: Complaints is a link, with its description.
- `src/lib/navigation/resource-href.ts`: complaints open from notifications.
- `src/features/orders/api/orders.schemas.ts`: `approvalBlockSchema`, shared with a refund's approval.
- `src/features/lookups/api/lookups.schemas.ts`, `src/mocks/data/lookups.ts`: complaint types.
- `src/mocks/data/complaints.ts`, `src/mocks/handlers/complaints.ts`, `src/mocks/handlers/index.ts`, `src/mocks/db.ts`, `src/mocks/data/reference.ts`, `src/mocks/data/permissions.ts`: the mock backend, following the backend's rules.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: CMPL-001…009.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/complaints/`: the records.

## Tests

**`src/features/complaints/api/complaints.test.ts`:**

- `[CMPL-001]`:
  - the list, newest first, with its count;
  - the filters, and the parameters sent to the backend;
  - a manager's queue and QC's queue;
  - the stats.
- `[CMPL-003]`:
  - raise, then submit: it gets a number and targets;
  - `missing_for_submit` names the missing fields; `nothing_defective`;
  - defective more than supplied is refused on the line;
  - edit the header and the products, refused once submitted;
  - cancel; delete.
- `[CMPL-004]`: approve with a severity and an owner; return; an officer refused; `status_changed`.
- `[CMPL-005]`: a date after today is refused on its field; the verdict.
- `[CMPL-002]`: the complaint's `can`, its history, and a contract violation.

**`src/features/complaints/components/complaints-ui.test.tsx`:**

- the list: rows, "Late", the counts, a status filter in the URL, a manager's queue, and nothing to do for Accounts;
- the form names every mistake;
- submit gets a number; a draft that isn't ready to submit says why; a returned draft shows its reason;
- the check needs a remark, approves, and returns, and closes when someone acted first;
- the QC rejection; QC has nothing to do before the check;
- cancel with a reason.

**By hand, in Chromium on the mock backend:**

- raise (mistakes first), submit, check and QC as Admin on a desktop in light mode;
- a District Manager's queue and a complaint on a phone in dark mode;
- axe found nothing on any of the screens.
