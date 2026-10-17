---
date: 2026-10-15
type: feature
title: "Masters: the offices"
dataIds:
  - MSTR-011
author: Nakul Srivastava
breaking: false
---

## Before

The backend serves the office tree (`backend/docs/api/org-units.md`):

- add an office: `POST /org-units`;
- rename, move or re-cover one: `PATCH /org-units/{id}`;
- close or reopen one: `POST /org-units/{id}/close`, `/reopen`.

The frontend only read open offices, for the office picker on the people forms. A new branch, or a district office closed after a reorganisation, needed the backend developer.

## Now

- **Offices** is the last tab of Masters.
  - It shows open offices by default, or Closed or All, searched by name, a page at a time.
  - Each office says where it sits ("Under Gujarat State" or "Top level"), the territory it covers (or "HQ unit"), its level named by the role that runs it ("District Manager"), and how many people work from it.
- **New office** asks for:
  - a name;
  - the level, from the roles ("2 · District Manager"); it can't change later;
  - the office it sits under, or "A top-level office, under none";
  - the territory it covers, or "An HQ unit, covering no territory".

  What's missing is named before sending. The backend refuses three things on their fields: a name already used beside it, a closed parent, and a move under one of its own offices.

- **Edit** renames, moves or re-covers an open office. It sends only what changed, and says "Nothing changed yet" until something does.
- **Close** is refused while people work from the office (`422 fields.id`). The row says so: "2 people still work from Rajkot District. Move them to another office, or deactivate them in Users & roles, then close it." **Reopen** brings a closed office back, from All.
- Every change refreshes the office pickers on the people forms too.
- Read-only without `masters.edit`.
- **The mock** adds `GET /org-units/{id}`, add, edit, close and reopen, with the backend's rules: a unique name among siblings, an open parent, no loops, and no closing while people are anchored. The list also filters by `parent_id`.
- Checked on a desktop in light mode and a phone in dark mode: the list with a refused close, editing, and a new office. axe found nothing.

## Discussion

- **Stacked on #134,** which adds the Masters page. Merge #134 first, then retarget this PR to `integration`.
- **Levels come from the roles list** (`GET /lookups/roles`), so the form doesn't hard-code what level 2 or 5 means.
- **Territories** (`/territories`) stay seeded; their admin is still listed as not built.
- **Not yet checked on staging.**

## Files changed

- `src/features/masters/api/masters.schemas.ts`, `masters.api.ts`, `masters.queries.ts`, `masters.mutations.ts`: the office schema, list, add, edit, close and reopen.
- `src/features/masters/components/offices-panel.tsx`: new, the list.
- `src/features/masters/components/office-dialog.tsx`: new, the add and edit form.
- `src/features/masters/components/masters.tsx`: the Offices tab.
- `src/components/layout/navigation.ts`: the page's description.
- `src/mocks/handlers/users.ts`: the office routes and rules.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: MSTR-011.
- `Docs/Plan.md` (§9.1, §9.3), `Docs/Tested-Features.md`, `Docs/screenshots/masters/`: records and screens.

## Tests

- `src/features/masters/api/masters.test.ts`, `[MSTR-011] Offices`:
  - open by default, closed when asked, with people counted;
  - added under an open office, and a name used beside it refused;
  - a move under its own office refused;
  - a busy office not closed, and an empty one closed and reopened;
  - refused without `masters.edit`.
- `src/features/masters/components/offices-ui.test.tsx`:
  - the list's place, territory, level and people;
  - why a busy office can't be closed;
  - reopening from All;
  - a new HQ unit at the top level, after its missing fields;
  - read-only without `masters.edit`;
  - the form's rules, and only what changed sent.
- Walked through in the mock: desktop light and phone dark.
