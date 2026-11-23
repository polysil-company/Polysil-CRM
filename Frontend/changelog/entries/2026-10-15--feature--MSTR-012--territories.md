---
date: 2026-10-15
type: feature
title: "Masters: the territories"
dataIds:
  - MSTR-012
author: Nakul Srivastava
breaking: false
---

## Before

The backend administers the territory tree (`backend/docs/api/territories.md`):

- `GET /territories`, filtered by level, parent and a search;
- `POST /territories`: a state at the root, or one level down under its parent;
- `PATCH /territories/{id}`: rename, or set the code.

Writes need `masters.edit`. Names are unique among siblings and codes unique per level. A state's code numbers its leads (`POL/<code>/…`) and locks once a lead is numbered with it (`code_locked`).

The frontend only searched territories in the pickers (`/lookups/territories`). A new state, district, taluka or village needed the backend developer.

## Now

- **Masters → Territories**, after Offices (`/masters?tab=territories`).
- **The list:**
  - states first, or all, districts, talukas or villages, searched by name or code;
  - each row shows its code, level and where it sits;
  - **Districts** (or Talukas, Villages) opens the level below inside it, shown as "In Gujarat" and cleared with its ×;
  - a locked state says its code can't change, and a state without a code says its leads can't be numbered.
- **New territory**, for `masters.edit`:
  - the level, then for anything but a state, the territory one level up, picked by name;
  - the name, and the code (optional except as the state's lead prefix, which the hint explains). The code is stored in capitals.
- **Edit**, for `masters.edit`:
  - rename, or set the code. A locked state's code field is disabled and says why;
  - a name taken among its siblings, a code taken at its level, or a locked code are refused in words.
- **After a change**, the territory lists refresh, and so do the territory pickers.
- **The top bar's description** for Masters mentions the territories.
- **The mock** follows `masters.py`: levels and parents, unique names and codes, the lock from the leads' numbers, and `masters.edit` for writes.
- Checked on a desktop in light mode and a phone in dark mode: the states, Gujarat's districts, a new taluka, and a locked state's edit. axe found nothing.

## Discussion

- **Stacked on #135** (offices), which is stacked on #134. Merge in order and retarget each to `integration` first.
- **In the mock, the admin list keeps its own copy of the tree.** A territory added there doesn't show in the pickers until a reload brings back the seed. On the backend both read the same table.
- **There is no delete or merge.** The backend offers neither.
- **Not yet checked on staging.**

## Files changed

- `src/features/masters/api/masters.schemas.ts`, `masters.api.ts`, `masters.queries.ts`, `masters.mutations.ts`: territories.
- `src/features/masters/components/territories-panel.tsx`, `territory-dialog.tsx`: new.
- `src/features/masters/components/masters.tsx`: the tab.
- `src/components/layout/navigation.ts`: the description.
- `src/mocks/handlers/territories.ts`: new; `src/mocks/handlers/index.ts`, `src/mocks/db.ts`, `src/mocks/data/territories.ts`: the mock.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: MSTR-012.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/masters/territories-*`: records and screens.

## Tests

- `src/features/masters/components/territories-ui.test.tsx`:
  - through the API: Gujarat's code locked and Uttar Pradesh's open; a locked code refused, a rename kept; a district without a parent refused, one under its state added with its code in capitals, a duplicate name refused; an employee may not add;
  - the tab: the states with the locked note, Gujarat's districts opened;
  - a new state with its code added; a locked state's code disabled;
  - an employee reads without New territory or Edit.
- Walked through in the mock: desktop light and phone dark.
