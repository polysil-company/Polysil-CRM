---
date: 2026-10-25
type: feature
title: Restore a deleted lead
dataIds:
  - LEAD-020
  - LEAD-019
  - RPT-001
author: Nakul Srivastava
breaking: false
---

## Before

Deleted leads (LEAD-019) was read only. A lead deleted by mistake stayed deleted, since the backend had no way to bring one back (BE-033). The list didn't say when or by whom a lead was deleted.

Two answers from the live test also waited on the backend:

- the dashboard's overdue count disagreed with Tasks (BE-036);
- whether a State Manager may delete leads (BE-037).

## Now

- **Restore** on each row of Deleted leads, for anyone who may delete and edit leads, as the backend requires.
  - It calls `POST /leads/{id}/restore` (BE-033, #206).
  - The lead goes back to the leads list with its owner, and the toast links to it.
  - A refusal says why, and the lead stays deleted.
  - The live list has no Restore.
- **When and by whom.** Each deleted row says "Deleted 20 Oct by Bharat Vaghela", from `deleted_at` and `deleted_by`.
- **The State Manager may delete and restore leads in the mock**, as RBAC.md §6.1 gives them (`V:org CED`, BE-037). The test box already granted it.
- **The dashboard card** now reads "Overdue follow-ups on leads", with "Lead tasks past their due date" beneath. The backend counts follow-ups on leads only (BE-036), which is why it can be lower than Tasks.

## Discussion

- **Who sees Restore.** `useCan("leads", "delete")` and `useCan("leads", "edit")` together, the backend's own pair. Hiding is a courtesy; the backend enforces it.
- **Opening a restored lead.** It's a link in the toast, not a toast button. A link needs no router in the cell and works with typed routes.
- **Not done:** an inactive owner. The backend keeps the owner even after they leave and suggests offering Assign. A lead's `owner` carries no active flag, so the frontend can't tell yet. The owner can be changed on the lead's page as usual.
- **`409 lead_deleted`** needs nothing new. Deleted leads aren't linked anywhere, and an error that slips through shows the backend's message, like any other conflict.

## Files changed

- `src/features/leads/api/leads.schemas.ts`: `deleted_at` and `deleted_by`, read as `deletedAt` and `deletedBy`.
- `src/features/leads/api/leads.api.ts`, `leads.mutations.ts`: `restoreLead` and `useRestoreLead`.
- `src/features/leads/components/restore-lead-button.tsx` (new), `leads-columns.tsx`, `src/features/leads/lib/lead-table-layout.ts`: the Restore column and the "Deleted … by …" line.
- `src/features/leads/components/leads-toolbar.tsx`: the notice no longer says they can't be brought back.
- `src/features/dashboard/components/dashboard-overview.tsx`: the card's label.
- `src/mocks/handlers/leads.ts`, `src/mocks/data/leads.ts`, `src/mocks/data/permissions.ts`: restore, stamps on delete, and the State Manager's grant.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: LEAD-020.
- `src/features/leads/components/lead-assign.test.tsx`: a router mock for the State Manager's Delete.
- Records: `Docs/Tested-Features.md`, `Docs/Live-Test-Report.md` (issues 6 and 10).

## Tests

**`leads-deleted.test.tsx`:**

- each deleted row has Restore, and going back to the live list removes it;
- a row says when and by whom; Restore makes one request with an idempotency key, then the lead leaves the deleted list and rejoins the leads;
- a State Manager opens Deleted leads and can restore;
- a refused restore says so, and the lead stays deleted;
- "neither offered nor shown" now signs in as a District Manager, who may not delete.

**`lead-assign.test.tsx`:** mocks `next/navigation`. These tests sign in as a State Manager, whose lead page now has Delete, which uses the router.
