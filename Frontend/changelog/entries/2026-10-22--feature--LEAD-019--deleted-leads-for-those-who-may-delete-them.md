---
date: 2026-10-22
type: feature
title: Deleted leads, for those who may delete them
dataIds:
  - LEAD-019
author: Nakul Srivastava
breaking: false
---

## Before

A deleted lead disappeared from every list. The backend can list deleted leads for a holder of `leads.delete` (`GET /leads?deleted=true`), but no screen asked for them. This was the first item of the plan's optional polish.

## Now

**Deleted leads** on the leads list, for holders of `leads.delete` (Admin in the mock):

- **Switching views:**
  - **Deleted leads** switches the list to the leads deleted so far. The address carries `?deleted=true`, so the view survives a refresh and can be shared.
  - **Back to leads** returns to the live list.
- **A note above the list** says nobody without the right to delete leads sees these, and that they can't be opened or brought back from here yet.
- **Rows:** the same columns as the live list, but the names are not links.
- **What stays and what goes:**
  - search, filters, sort, paging and **Download Excel** work on the deleted list;
  - **New lead** and **Possible duplicates** are hidden.
- **Empty:** "No deleted leads". With filters on, the usual "No leads match these filters".
- **Without `leads.delete`:** the button is absent. Opening `?deleted=true` by its address shows the live list, and nothing asks for deleted leads.

**Mock:**

- deleting a lead moves it to the deleted list, as the backend's soft delete does;
- two deleted leads are seeded, as copies of seeded leads, so no other count moves.

**Records brought into `integration`:**

- **BE-032** (the tracking app's device token), which #194 refers to;
- the two handoff files (`Docs/handoff-21oct-2026.md` and `Docs/handoff-mobile-app.md`).

All three had stayed on a working branch.

## Discussion

- **Read-only, for now.** The backend says the list exists "to restore one", but has no restore endpoint, and its rows don't say when or by whom a lead was deleted. **BE-033** asks for:
  - `POST /leads/{id}/restore`;
  - `deleted_at` and `deleted_by` on the rows;
  - whether a deleted lead's page opens.

  A **Restore** button follows when it lands.

- **Why the names aren't links:** a lead's page offers edits and stage changes. Doing that on a deleted lead nobody else can see would be confusing, and the backend hasn't said whether the page opens at all.
- **The flag is optional on `LeadListParams`:** five other callers build the list's parameters (the order and visit lead pickers, three tests). Left out, it means the live list, as the backend's own default does.

## Files changed

- `src/features/leads/api/leads.schemas.ts`: `deleted` on `LeadListParams`.
- `src/features/leads/api/leads.api.ts`: list and export send `deleted=true` only when asked.
- `src/features/leads/hooks/use-lead-list-params.ts`: `deleted` in the URL, honoured only with `leads.delete`; `setDeleted`.
- `src/features/leads/components/leads-toolbar.tsx`: the switch, the note, and New lead and duplicates hidden in the deleted view.
- `src/features/leads/components/leads-table.tsx`: the deleted columns and the empty state.
- `src/features/leads/components/leads-columns.tsx`: `deletedLeadColumns`, names without links.
- Mock:
  - `src/mocks/db.ts`: `deletedLeads`;
  - `src/mocks/data/leads.ts`: `seedDeletedLeads`;
  - `src/mocks/handlers/leads.ts`: `deleted=true` for a deleter; delete keeps the lead.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: LEAD-019.
- `docs/Backend-Tasks.md`: BE-033; BE-032 brought in.
- Records:
  - `Docs/Tested-Features.md`;
  - `Docs/plan-13oct-2026.md`;
  - `Docs/handoff-21oct-2026.md` and `Docs/handoff-mobile-app.md`, brought in.

## Tests

`src/features/leads/components/leads-deleted.test.tsx`, 4 tests in `[LEAD-019] Deleted leads`:

- a deleter switches to the deleted leads, with `deleted=true` sent and kept in the URL; names aren't links; New lead and duplicates are hidden; Back to leads returns;
- a lead deleted through `DELETE /leads/{id}` appears in the list;
- "No deleted leads" when there are none;
- without `leads.delete`: no button, and the address shows the live list without asking for deleted leads.

To check by hand in the mock, choose Preview as role → Admin, then:

1. Open **Leads** and select **Deleted leads**: two leads, with the note above them.
2. Select **Back to leads**.
