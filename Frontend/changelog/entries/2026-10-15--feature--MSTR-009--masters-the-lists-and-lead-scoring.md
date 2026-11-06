---
date: 2026-10-15
type: feature
title: "Masters: the lists and lead scoring"
dataIds:
  - MSTR-009
  - MSTR-010
  - MSTR-001
author: Nakul Srivastava
breaking: false
---

## Before

Admin → Masters sat in the menu marked "Soon". The backend serves the writes for every list behind the pickers (`backend/docs/api/lookups.md`):

- lead sources, irrigation systems, lost reasons, crops, meeting types and complaint types: add a row (`POST /lookups/{list}`), switch one on or off (`PATCH /lookups/{list}/{id}`);
- the lead score's weights, caps and bands: `GET`/`PATCH /lookups/scoring`.

Nothing in the frontend wrote them, so a new lead source or lost reason needed the backend developer.

## Now

- **Masters** opens at `/masters`, for staff who see masters. It has one tab per list, then Lead scoring, and the open tab is kept in the URL. Those with `masters.edit` change things; everyone else reads them.
- **Each list** shows every row's name, code and status ("In use" or "Switched off"), with how many are in use.
  - **Add a lead source** (and the same for every list) asks for a name and a code. The code follows the name ("Krishi Mela" → `krishi_mela`) until it is typed.
  - Sources and reasons also take a sort order. Sources take a quality from 0 to 1. Reasons take Lost or Won.
  - A missing name, a misshapen code, a code already in use, or a quality outside 0 to 1 is named on its field before sending. The backend's refusals land on the same fields.
  - **Switch off** keeps the row: records that use it keep it, and new ones can't pick it. **Switch on** brings it back. Rows are never renamed or deleted, as the backend allows (ADR-033).
  - Every picker that reads the list refreshes.
- **Lead scoring** lists the four weights (with what they add up to), the value cap, the fast and slow contact hours, the engagement cap, and the hot and warm bands. Each setting says what it does, from the backend's formula.
  - **Save the settings** sends only what changed.
  - A cap or an hour band of 0 is refused on its field, as the backend refuses it.
  - Any setting the backend adds later shows under "Other".
- **The menu item** is live and staff only.
- **The mock:**
  - the lists live in the mock database;
  - the writes are refused without `masters.edit`;
  - the score settings start from the backend's seed (migration 006).
- Checked on a desktop in light mode and a phone in dark mode, as Admin: a list, adding a source, and lead scoring. axe found nothing.

## Discussion

- **BE-026, new:** the lists answer only `id`, `code`, `name` and `is_active`. So a source's quality and a row's sort order can be set when it is added, but not shown or changed afterwards. Masters asks for them only on add until the list returns them.
- **Offices** (`/org-units`) are the rest of plan item 8, in the next PR, as another Masters tab.
- **The mock's other screens** still read the seeded lists. A row added here shows in Masters and in the pickers that read `GET /lookups/{list}`, but the mock's lead and complaint handlers don't know it.
- **Not yet checked on staging.**

## Files changed

- `src/features/masters/api/masters.schemas.ts`, `masters.api.ts`, `masters.queries.ts`, `masters.mutations.ts`: new. The writes, the score settings, and which list takes which field.
- `src/features/masters/components/masters.tsx`: new, the page and its tabs.
- `src/features/masters/components/lookup-list-panel.tsx`: new, one list with Add and Switch off/on.
- `src/features/masters/components/scoring-panel.tsx`: new, the score settings.
- `src/app/(app)/masters/page.tsx`: new, the route.
- `src/components/layout/navigation.ts`: Masters is live, staff only.
- `src/mocks/data/lookups.ts`, `src/mocks/db.ts`, `src/mocks/handlers/lookups.ts`: editable lists, the writes and the score settings.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: MSTR-001 retitled; MSTR-009 and MSTR-010.
- `../docs/Backend-Tasks.md`: BE-026.
- `Docs/Plan.md` (§9.1, §9.3), `Docs/Tested-Features.md`, `Docs/screenshots/masters/`: records and screens.

## Tests

- `src/features/masters/api/masters.test.ts`:
  - `[MSTR-009]`: a row added and listed; a used code refused on its field; switched off and on, kept in the list; refused without `masters.edit`.
  - `[MSTR-010]`: settings read, and only those sent changed; a zero cap and an unknown key refused by name.
- `src/features/masters/components/masters-ui.test.tsx`:
  - `[MSTR-009]`: read-only without `masters.edit`; adding a source with its code following the name; switching a complaint type off from its tab; the form's rules and the request it sends.
  - `[MSTR-010]`: only the changed setting saved; a zero cap refused on its field; read-only without `masters.edit`; the setting text helpers.
- Walked through in the mock: desktop light and phone dark.
