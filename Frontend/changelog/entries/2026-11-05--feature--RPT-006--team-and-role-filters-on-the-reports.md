---
date: 2026-11-05
type: feature
title: Team and role filters on the reports
dataIds:
  - RPT-006
author: Claude
breaking: false
---

## Before

- The backend's FS-082 (backend #226, 5 Nov) added two filters to every report that takes a person, and to the forecast, insights and territory performance:
  - `team_of`: a person and everyone below them on the org chart, refused with `404 not_in_your_line` outside the caller's line, and never with `owner_id`;
  - `roles`: up to 10 role codes, only people holding one of them now.
- Salesperson performance now gives every team member a row, zeros included, with `role` and `office`.
- The reports offered only one person.

## Now

- **Team** and **Roles** filters on those reports, beside Person:
  - **Team** picks from the same people as Person (you, then the staff below you). Choosing a team drops the person, and choosing a person drops the team.
  - **Roles** offers the staff roles from `GET /lookups/roles`, never the partners', up to 10.
  - Both live in the URL (`?team=`, `?roles=`), are cleared by **Reset filters**, and go into the Excel, CSV and PDF files.
- **Salesperson performance** shows each person's role and office under the name, so a row of zeros still says who it is.
- **The mock** reads `team_of` and `roles`: a team is the person and every active staff member at a lower level, since the seeds sit in one state. It refuses someone unknown with `404 not_in_your_line`, and both filters with `owner_id`.

## Discussion

- **The same people list for Team as for Person.** `GET /tasks/assignees` is already "you and the staff below you", which is exactly who the backend lets a team be built around. An admin with `users.view` at global scope could pick anyone, but that list already holds everyone for them.
- **The person wins over the team.** The backend refuses both together, so an address carrying both drops the team rather than showing a refusal.
- **Dealer performance and complaints** don't take the filters, as on the backend.

## Files changed

- `src/features/reports/api/reports.schemas.ts`: `teamOf` and `roles` on the params; the echoed filters; `role` and `office` on a salesperson row.
- `src/features/reports/api/reports.api.ts`: `team_of` and `roles` in the query.
- `src/features/reports/lib/report-catalogue.ts`: which reports take a team.
- `src/features/reports/components/report-view.tsx`: the Team and Roles filters.
- `src/features/reports/components/report-bodies.tsx`: role and office under the person.
- `src/mocks/handlers/reports.ts`: teams, roles and every team member's row.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: RPT-006.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md` (items 50 and 51): records.

## Tests

- `[RPT-006] Team and role filters on the reports (FS-082)`:
  - the query carries `team_of` and `roles`, and every row has a role and office;
  - `not_in_your_line` comes back as a 404;
  - picking a team drops the person and shows role and office;
  - only staff roles are offered.
- The existing report and forecast tests pass with the new params.
