---
date: 2026-11-05
type: feature
title: The org chart
dataIds:
  - ADMN-008
author: Claude
breaking: false
---

## Before

- The backend's FS-080 added `GET /users/org-chart`:
  - who reports to whom, worked out from office and role (migration 083), with nothing stored, so it follows any change at once;
  - any staff member sees their own line and everyone below them;
  - someone who sees every user sees the whole company.
- The frontend had no org chart. "Whom do I report to?" and "who is in my team?" had no answer on screen.

## Now

- **Overview → Org chart** (`/org-chart`), for all staff; partner users don't see it.
- **Your line:**
  - the managers above you, nearest first;
  - a step can hold two people ("Nirav Shah and Mehul Patel") when two at the same level in one office both manage;
  - at the top, "Nobody above: the top of the line".
- **Your team:**
  - everyone below you, counted by role ("District Manager: 1", "Field Officer: 3");
  - a tree drawn from each person's first manager;
  - each person with their role, office, and how many report to them directly and in all;
  - someone with two managers says "Also reports to …";
  - the first level is open, and deeper teams fold open and closed.
- **A person's name opens their own picture** (`?user=`), with "Back to my team". Someone who isn't below you, or has left, says "No reporting line to show".
- **Whole company** (`?view=company`):
  - for someone who sees every user (`users.view`), from the tabs at the top;
  - its roots are the people nobody manages;
  - staff the backend can't place (on the System office) are named in a warning, to be given a real office;
  - anyone else who opens it is told it isn't theirs to see.
- **States:** a skeleton while loading, and the error box with a reference on failure.

## Discussion

- **The tree is drawn under each person's first manager.** The backend sorts the managers by name and says to do exactly that, showing the rest as "also reports to". Nobody appears twice.
- **The whole-company tab shows for anyone with `users.view`.** The endpoint wants it at global scope, which the permission summary on `/auth/me` doesn't say. A scoped holder who opens it gets the backend's 403, shown in words. That's better than hiding it from someone who may.
- **No search or zoom yet.** The mock's company is a handful of people. The client's is about 3,000, so a search box or a collapsed company view may be wanted once it is seen on real data.
- **The mock** works out managers as `reporting_lines()` does:
  - the nearest higher line role, not a functional one, in the person's own office or the offices above;
  - every mock role shares one session, so "me" is the first person seeded with the signed-in role (Ravi the field officer, Nirav the district manager, Asha the state manager);
  - its route sits before `/users/:userId`, so "org-chart" isn't read as an id.

## Files changed

- `src/features/org-chart/` (new): the contract, the call and query, the page and tests.
- `src/app/(app)/org-chart/page.tsx` (new): the route.
- `src/components/layout/navigation.ts`: Org chart under Overview, for staff.
- `src/mocks/handlers/org-chart.ts` (new), and `index.ts`: the chart worked out from the mock's people and offices.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: ADMN-008.
- `Docs/Plan.md` §9.1, `Docs/plan-13oct-2026.md`, `Docs/Tested-Features.md`, `Docs/screenshots/org-chart/`: records and screens.

## Tests

- **`[ADMN-008] The org chart, through the API`:**
  - a field officer's line, nearest first;
  - a manager's team counted by role, and the picture of someone below;
  - nobody above may be opened (404);
  - the whole company only for `users.view` (403 otherwise).
- **`[ADMN-008] OrgChartView`:**
  - the team as a tree, a team folding away, and each name linking to its picture;
  - a field officer's line with "Nobody reports to you";
  - "No reporting line to show";
  - the whole company as Admin.
