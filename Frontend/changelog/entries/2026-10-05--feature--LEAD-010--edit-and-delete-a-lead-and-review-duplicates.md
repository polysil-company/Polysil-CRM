---
date: 2026-10-05
type: feature
title: Edit and delete a lead, and review duplicates
dataIds:
  - LEAD-010
  - LEAD-011
  - LEAD-012
author: Nakul Srivastava
breaking: false
---

## Before

A lead's details couldn't be corrected once it was saved: a mistyped mobile or the wrong village stayed. A lead couldn't be deleted. A lead's page listed its possible duplicates, but nobody could act on them. The backend has served all three since the leads module (`PATCH`/`DELETE /leads/{id}`, `GET /leads/duplicates`, `POST /leads/duplicates/{id}/dismiss`, `POST /leads/{id}/merge`).

## Now

- **Edit** sits beside Assign on an open lead, for whoever may edit leads.
  - It has the same fields as New lead: name, mobile, email, territory, village, type, system, source, value, crops and land.
  - Only the fields that changed are sent.
  - A refused field is named on the form.
  - A closed lead (won, lost or merged) has no Edit. If the backend refuses one anyway (`stage_terminal`), the dialog explains why.
  - The history says which fields changed.
- **Delete**, for holders of `leads.delete` (Admin in the mock): it asks first, then goes back to the list. The lead's pending duplicate pairs close.
- **Possible duplicates** (`/leads/duplicates`), reached from the leads toolbar and from "Review and merge" on a lead's duplicate notice.
  - Each pair shows side by side: name, stage, inquiry, mobile, place, owner, value and created, with what matched and how strongly.
  - **Keep** one lead to merge the other into it. A confirmation first says the merged lead's history moves across and that this can't be undone.
  - **Not a duplicate** clears the pair.
  - A pair with a won or lost lead says it can't be merged and offers only Not a duplicate, since the backend refuses that merge (`merge_terminal`).
  - States: skeleton, "No possible duplicates", Show more, and a phone in dark mode.

## Discussion

- **One set of lead fields.** New lead's fields became `LeadFields`, shared with Edit, so the two forms can't drift. The first note stays on New lead only.
- **The patch is a diff.** The form's values are parsed the same way as on New lead, then compared with the lead as loaded. Only the keys that differ go to the backend, which leaves the rest alone.
- **Merge from the queue only.** The queue shows both leads side by side, so the user sees what they are merging. A lead's notice links there rather than offering a blind merge.

**The mock:**

- A deleted lead is dropped. The backend hides it from everyone but holders of `leads.delete`.
- The queue leaves out pairs with a lead already merged, since the backend re-points those when the lead merges.

## Files changed

- `src/features/leads/components/`:
  - `lead-fields.tsx`: new; the fields from `new-lead-dialog.tsx`, which now uses it.
  - `lead-edit-dialog.tsx`: new; `LeadEditDialog` and `LeadDeleteDialog`.
  - `duplicate-review.tsx`: new.
  - `lead-detail.tsx`: Edit, Delete, and Review and merge.
  - `leads-toolbar.tsx`: Possible duplicates.
  - `lead-edit.test.tsx`: the UI tests.
- `src/features/leads/api/`:
  - `leads.schemas.ts`: `PatchLeadRequest`, the duplicate pair and page, the dismiss result, `MergeLeadRequest`.
  - `leads.api.ts`, `leads.queries.ts`, `leads.mutations.ts`: the new calls.
  - `leads-edit.test.ts`: the API tests.
- `src/app/(app)/(sales)/leads/duplicates/page.tsx`: the route.
- `src/mocks/handlers/leads.ts`: `PATCH`, `DELETE`, the queue, dismiss and merge, with the backend's refusals.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: LEAD-010…012.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/leads/`: the records.

## Tests

**`src/features/leads/api/leads-edit.test.ts`:**

- `[LEAD-010]`: only what is sent changes, and the history records it; a closed lead is refused.
- `[LEAD-011]`: delete for a holder of `leads.delete`; 403 for an employee.
- `[LEAD-012]`: the queue, dismiss, and merge into the survivor; `merge_self` and `merge_terminal` are refused.

**`src/features/leads/components/lead-edit.test.tsx`:**

- Edit sends only the farmer's name, and a closed lead has no Edit.
- Delete asks, then leaves; a manager without `leads.delete` sees no Delete.
- The queue dismisses a pair and merges after confirming; a pair with a closed lead offers no merge; the empty state shows.

All 145 lead tests pass, New lead's included.

**By hand, in Chromium on the mock backend, as Admin:**

1. The queue, and the merge dialog.
2. A lead with a duplicate.
3. Editing a contacted lead's village.
4. The delete dialog.
5. The queue on a phone in dark mode.

axe found nothing on any of these.
