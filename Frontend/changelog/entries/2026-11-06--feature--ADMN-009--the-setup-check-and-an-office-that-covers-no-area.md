---
date: 2026-11-06
type: feature
title: The setup check, and an office that covers no area
dataIds:
  - ADMN-009
author: Claude
breaking: false
---

## Before

- The backend's FS-082 (backend #226) added:
  - `GET /users/setup-check`, which reports what is set up wrong. Each of five checks comes with its count, a title, why it matters, and the first 100 people or partners to fix. It needs `users.edit` at global scope; anyone else gets `403`.
  - A new refusal on `POST /users` and `PATCH /users/{id}`: a Field Officer or District Manager put in an office that covers no area gets `422 office_has_no_area`, on `org_unit_id` or `role`.
- Neither had a place in the app.

## Now

- **The setup check on the dashboard**, for those who may change people:
  - **A card for anything to fix:** each check with something to fix gets its count, why it matters, and the first five people or partners. Each name links to their page (a person's to `/users/{id}`, a partner's to `/partners/{id}`). **Show all** shows the rest of the backend's first 100.
  - **When nothing needs fixing,** one line says so.
  - **Hidden** for anyone without the permission, or with it for only part of the company.
- **The person form** already places a refusal's fields on its own fields, so `office_has_no_area` shows on **Office**, or on **Role**, with the backend's words.
- **The mock:**
  - runs the five checks on its seeds. Junagadh and Amreli have no District Manager, so their field officers skip a level;
  - refuses an area role in an office with no area, on a change of role or office only, as the backend does.

## Discussion

- **On the dashboard, above the figures.** The backend calls it "for the admin dashboard". The administrators who can fix these things land there first, and the card takes no room when there is nothing to fix.
- **A 403 shows nothing.** A user may hold `users.edit` for one area only, and the check needs global scope. An error card there would only say what they can't see.
- **Which roles need an area is still open** on the backend (GAP-556, client question 37.4). The mock follows the backend's current set: Field Officer and District Manager.

## Files changed

- `src/features/users/api/users.schemas.ts`, `users.api.ts`, `users.queries.ts`: the setup report and its call.
- `src/features/users/components/setup-check-card.tsx`: the card and its skeleton.
- `src/features/dashboard/components/dashboard-overview.tsx`: the card above the figures.
- `src/mocks/handlers/users.ts`: the setup check, and `office_has_no_area`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: ADMN-009.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`: records.

## Tests

- `[ADMN-009] The setup check (FS-082)`:
  - every check comes back in order, and a field officer is refused;
  - the card lists a check with people linked to their pages;
  - the one line when nothing needs fixing;
  - nothing for someone without the permission, or on a 403.
- `[ADMN-009] An office that covers no area`: moving a Field Officer to an office with no area is refused on `org_unit_id`.
