---
date: 2026-11-05
type: feature
title: A restore in the lead's history, and an owner who has left
dataIds:
  - LEAD-020
author: Claude
breaking: false
---

## Before

Restoring a deleted lead (LEAD-020, PR #210) left two gaps against `leads.md`:

- **The history:** the backend adds `lead.restored` to a lead's history, with `duplicates_reopened`. The history had no line of its own for it, so it showed a generic "Lead restored" label and dropped the reopened pairs.
- **An owner who has left:** the restore keeps the owner, even one who has since left, and the backend says to "offer Assign when `owner` is inactive". A lead's `owner` carries no active flag, so the screen couldn't tell.

## Now

- **The history** reads "<name> restored the lead", with ", and its possible duplicate is open again" or ", and its 2 possible duplicates are open again" when the restore reopened them. It has an undo icon in the success tone.
- **The restore's toast**, when the lead's owner has left, adds "Its owner, Hiren Mehta, has left: open it and assign it to someone." beside the link to the lead.
- **BE-042** asks the backend for `is_active` on a lead's `owner`. Until it comes, the lead is restored as before and nothing more is said.

## Discussion

- **Why not work out "has left" on the frontend.** `GET /leads/assignees` lists only the people the caller may assign to. An owner missing from it may simply be in another area, so "has left" would sometimes be wrong. Asking the backend for the flag gives the right answer every time, and the frontend reads it as soon as it arrives.
- **Assign isn't opened from the toast.** Assign is a dialog on the lead's page, with no address of its own. The toast links to the lead and says to assign it.

## Files changed

- `src/features/leads/lib/timeline-entries.ts`, `src/features/leads/components/lead-timeline.tsx`: the `restored` entry, its sentence and icon.
- `src/features/leads/api/leads.schemas.ts`: the owner's `is_active`, read when sent.
- `src/features/leads/components/restore-lead-button.tsx`: the toast for an owner who has left.
- `docs/Backend-Tasks.md`: BE-042.
- `Docs/plan-13oct-2026.md`, `Docs/Tested-Features.md`: records.

## Tests

- `[LEAD-005] toTimelineEntry › [LEAD-020] reads a restore`: with the reopened count, and without it.
- `[LEAD-019]` Deleted leads: a restored lead whose owner has left gets the toast's line.
