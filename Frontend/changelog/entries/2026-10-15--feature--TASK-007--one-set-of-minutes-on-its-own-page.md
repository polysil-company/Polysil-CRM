---
date: 2026-10-15
type: feature
title: "One set of meeting minutes on its own page"
dataIds:
  - TASK-007
author: Nakul Srivastava
breaking: false
---

## Before

A task created from meeting minutes said "From meeting minutes" as plain text. The minutes themselves showed only on the lead's page, in a list. From My day, Team or All tasks there was no way to read the meeting a task came from without finding the lead first. The backend's `GET /minutes/{id}` (`tasks-and-planner-contract.md`) was registered under TASK-007 but unused.

## Now

- **"From meeting minutes"** on an action item's task is a link, wherever the task shows: My day, Team, All tasks and a lead's tasks.
- **It opens `/tasks/minutes/{id}`**, which shows:
  - the meeting's date;
  - the lead it was about, as a link, or the partner;
  - who was there and the notes;
  - each action item as its task stands now ("1 of 2 done", overdue in red);
  - who recorded the minutes.
- **The page sits under Tasks,** so the Tasks menu rule decides who opens it (APP-006), and Tasks stays highlighted. Minutes out of scope (`404`) show "Page not found"; other failures show the error with a retry.
- **Shared view:** the lead's minutes card and the page show the same view (`MinutesContent`). The minutes now carry their lead and partner.
- **The mock** serves `GET /minutes/{id}`.
- Checked on a desktop in light mode and a phone in dark mode: the link on a task, the page, and minutes not found. axe found nothing.

## Discussion

- **Under `/tasks`, not `/minutes`:** a page outside the menu map is open to anyone signed in, and minutes are staff only.
- **No new Data ID:** `GET /minutes/{id}` was already listed under TASK-007.

## Files changed

- `src/features/tasks/api/tasks.schemas.ts`, `tasks.api.ts`, `tasks.queries.ts`: the minutes' lead and partner, `getMinutes`, `minutesQueryOptions`.
- `src/features/tasks/components/minutes-detail.tsx`: new, the page.
- `src/app/(app)/tasks/minutes/[minutesId]/page.tsx`: new, the route.
- `src/features/tasks/components/lead-minutes.tsx`: `MinutesContent`, shared with the page.
- `src/features/tasks/components/task-row.tsx`: the link.
- `src/mocks/handlers/tasks.ts`: `GET /minutes/{id}`.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/tasks/minutes-*`: records and screens.

## Tests

- `src/features/tasks/components/minutes-detail.test.tsx`:
  - `getMinutes` reads the minutes with each action item as it stands, and a 404 for unknown ones;
  - the page shows the meeting, the linked lead, "1 of 2 done", the action items and the notes;
  - minutes out of scope are not found;
  - a lead's action-item task links to the page.
- Walked through in the mock: desktop light and phone dark.
