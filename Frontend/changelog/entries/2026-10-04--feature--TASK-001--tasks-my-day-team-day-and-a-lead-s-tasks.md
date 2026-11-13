---
date: 2026-10-04
type: feature
title: "Tasks: my day, team day and a lead's tasks"
dataIds:
  - TASK-001
  - TASK-002
  - TASK-003
  - TASK-004
  - TASK-005
author: Nakul Srivastava
breaking: false
---

## Before

Tasks was a "Soon" item in the sidebar. The backend has served tasks, the planner and meeting types since #25 (`backend/docs/api/tasks.md`, handover `tasks-and-planner-contract.md`). Follow-ups were dates on a lead, and nobody could see their day's calls and visits in one place, or a manager their team's.

## Now

**Tasks page** (`/tasks`, staff with `tasks`; dealers have none):

- **My day.** What is overdue from earlier sits on top (up to 90 days back). Below it, what is due that day, by time.
  - Each task shows its kind (call, visit, meeting, follow-up, other), time, meeting type, the lead (linked) or dealer it is about, who gave it, and its notes.
  - Done tasks say what happened; cancelled ones say why.
  - Overdue is the server's word; the screen never works it out.
- **The day** moves back and forward, jumps to any date, or returns to today. It is kept in the URL (`?date=`). A future day has nothing overdue.
- **Team**, for anyone with people below them: one row per person, with due that day, done that day and overdue now.
  - People with nothing to do are listed too.
  - A row opens that person's day (`?user=`, so it can be sent as a link). "Back to team" returns, and a new task from there is for that person.
  - Officers, Accounts, Dispatch and QA see no Team.
- **New task:** what to do, the kind, the day, and an optional time (left empty, it is due at 18:00). Then who it is for (yourself first, then the people below you, from `GET /tasks/assignees`) and notes. Server field errors land on their fields, and a retry reuses its Idempotency-Key.
- **Done** asks what happened, and for a meeting whether the gift was shown. **Cancel** asks why.
  - A task someone else gave you isn't offered for cancelling: only they can (the backend's rule).
  - **Reopen** a done task as its assignee or its giver. After 7 days the backend says to add a new one.
  - A task someone moved on meanwhile closes the dialog and refreshes the list.

**On a lead's page,** a "Tasks and meetings" card:

- What is still to do comes first, then what was done or cancelled, each saying who it is for.
- "Add task" makes a task about the lead. A meeting there names its kind (Survey & Design, Follow-up…, from `GET /lookups/meeting-types`).
- A merged lead takes no new tasks.

**States covered:**

- skeletons that mirror the rows;
- "A clear day" and "No tasks yet";
- errors with retry;
- a later page failing without losing what is shown;
- phone and desktop, light and dark.

## Discussion

- **Split in two.** This pull request is the daily loop: see the day, add, finish, cancel, reopen. Three things follow in the next one, each already registered:
  - meeting minutes with action items (TASK-007);
  - editing and reassigning a task (TASK-006);
  - the full task list with filters and Excel export (TASK-008).
- **Who sees Team.** It is decided from the `tasks` grant's scope in `/auth/me` (anything wider than `own`), not from the role name. That matches the backend's 403 for someone with no team.
- **Cancelling is hidden** for a task given by someone else rather than shown and refused, because the backend's rule is simple to mirror. Reopening isn't hidden after 7 days: that needs the clock, and the backend's refusal explains it.
- **Mock users.** In the mock, the signed-in user (usr-001) has a seeded day: six tasks today, three overdue from earlier in the week, and a spread of work for the five people below them.
- **Pre-existing issue found during the walk.** axe flags the contrast of superseded quotation versions on a lead's page (`opacity-70` in `lead-quotations.tsx`). It isn't part of this change; it is noted as a follow-up.

## Files changed

- `src/features/tasks/api/`: `tasks.schemas.ts` (Task, PlannerDay, TeamPage, the requests, the form schema), `tasks.api.ts`, `tasks.queries.ts`, `tasks.mutations.ts`, `tasks.test.ts`.
- `src/features/tasks/lib/task-labels.ts`: kinds, icons, what a task is about, and the backend's refusals in plain words.
- `src/features/tasks/hooks/use-task-params.ts`: the view, day and person in the URL; `useHasTeam`.
- `src/features/tasks/components/`:
  - `tasks-view.tsx`, `planner-day.tsx`, `team-day.tsx`, `task-row.tsx`;
  - `task-action-dialog.tsx`, `new-task-dialog.tsx`, `lead-tasks.tsx`;
  - `tasks-ui.test.tsx`.
- `src/app/(app)/tasks/page.tsx`, `loading.tsx`: the route.
- `src/components/layout/navigation.ts`: Tasks is a link, for staff, with its description.
- `src/features/leads/components/lead-detail.tsx`: the Tasks and meetings card.
- `src/features/lookups/api/lookups.schemas.ts`, `src/mocks/data/lookups.ts`: the meeting types list.
- `src/lib/format/date.ts`, `index.ts`, `format.test.ts`: `shiftCalendarDay` and `formatCalendarDay`.
- `src/mocks/data/tasks.ts`, `src/mocks/handlers/tasks.ts`, `src/mocks/handlers/index.ts`, `src/mocks/db.ts`, `src/mocks/data/reference.ts`: the mock backend, following the backend's rules (one link, meeting types, who may cancel or reopen, the 7-day window, 409 when not open, idempotent replays).
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: TASK-001…008.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/tasks/`: the records.

## Tests

- **`src/features/tasks/api/tasks.test.ts`:**
  - `[TASK-001]`: the day's order and its overdue tasks; nothing overdue on a future day; a team member's day; a contract violation.
  - `[TASK-002]`: the team rows; a 403 without a team.
  - `[TASK-003]`: a lead's tasks with the total; a hidden link.
  - `[TASK-004]`:
    - assignees for a manager and for an officer;
    - the form becoming the request (a date alone, or a date and time in India);
    - the meeting type rule;
    - creating a meeting on a lead;
    - an idempotent replay;
    - `not_assignable` on its field.
  - `[TASK-005]`: complete then reopen; 409 when no longer open; cancel with a reason; 403 for a task someone else gave.
- **`src/features/tasks/components/tasks-ui.test.tsx`:**
  - My day: order, sections and summary; day navigation in the URL; mark done (a reason is required); cancel (not offered on a task someone else gave); a new task appearing in the day; error; empty.
  - Team: hidden from officers; the rows; opening a person's day and going back.
  - LeadTasks: the groups; adding a meeting that needs its kind; nothing new on a merged lead.
- **`src/lib/format/format.test.ts`:** day shifting across months and years, and the day heading.
- **By hand, in Chromium on the mock backend:**
  - My day, mark done, new task, Team, a person's day and a lead's card on a desktop in light mode;
  - My day and new task on a phone in dark mode;
  - axe found nothing on the task screens.
