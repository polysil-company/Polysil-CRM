---
date: 2026-10-18
type: feature
title: Tasks for dealers
dataIds:
  - TASK-009
author: Nakul Srivastava
breaking: false
---

## Before

Staff could give tasks only to staff, and dealer users had no tasks screen.

## Now

Built to `dealer-tasks-contract.md` (FS-037). The admin switches it on with the `tasks_for_dealers` setting; until then nothing changes for dealers.

**Giving a dealer a task**

- New task's **For** asks for `include_partners`. While the setting is on, it lists the users of the dealers the manager can see under a **Dealers** heading, below **Our team**, each with the dealer's name ("Bhavesh Shah · Shah Agro Traders").
- A task about a lead or order the dealer can't open is refused on the For field (`link_not_visible_to_assignee`), with a message that says so.
- Team filters, reports, minutes and reassigning keep to staff, through `staffAssigneesQueryOptions`. Dealers appear only when giving a new task.

**A dealer's Tasks page** (`/my-tasks`)

- **To do** and **Done** views. Each task shows when it is due, what it is about, and who gave it.
- **Done** opens the existing done dialog to say what happened. It is the only action: no edit, cancel, reopen or minutes link.
- The page has loading, empty and error states, plus **Show more**.

**When the setting is off**

- A dealer can't read the setting, and the backend refuses every tasks route while it is off. So the dealer's menu asks once for their open tasks (the page reuses the answer) and shows the **Tasks** item only when that works.
- Opened directly, the page says tasks aren't switched on.
- This uses a new `NavItem.gate`, with `useNavGates` in the sidebar and the command menu.

**Mock**

- Portal roles hold `tasks` view and edit on their own tasks, honoured only while the setting is on.
- Assignees take `include_partners`.
- A dealer completes their tasks; editing, cancelling, reopening and creating answer 403.
- A task for a dealer about someone else's lead or order is refused.

Walked as Admin, then switched to Dealer on a desktop in light mode and a phone in dark mode. Axe found nothing on the dealer's page, with no console errors and no sideways scroll. With the setting off, the dealer has no Tasks item.

## Discussion

- **Why the menu probes the backend.** Showing the item from permissions alone would show it while the setting is off, because portal roles hold `tasks` either way. Reading `/settings` isn't possible for a dealer. Asking for the open tasks costs one request, which the page then reuses.
- **The route guard doesn't use the gate.** The page itself says when tasks are off.
- **`mockSettings` is now exported from the settings mock,** the same change as in PR #166, so the two merge cleanly.

## Files changed

- `src/features/tasks/api/tasks.schemas.ts`: assignees carry `kind` and `partner`.
- `src/features/tasks/api/tasks.api.ts`: `include_partners=true`.
- `src/features/tasks/api/tasks.queries.ts`: `staffAssigneesQueryOptions`.
- `src/features/tasks/components/new-task-dialog.tsx`: the Our team and Dealers groups.
- `src/features/tasks/components/{all-tasks,tasks-view,minutes-dialog,edit-task-dialog}.tsx` and `src/features/reports/components/report-view.tsx`: staff only.
- `src/features/tasks/lib/task-labels.ts`: the refusal covers dealers.
- `src/features/tasks/components/task-row.tsx`: a `completeOnly` mode.
- `src/features/tasks/components/dealer-tasks.tsx` and `src/app/(app)/my-tasks/page.tsx`: new, the dealer's page.
- `src/features/tasks/hooks/use-dealer-tasks.ts`: new, `dealerTaskParams` and `useDealerTasksOn`.
- `src/components/layout/navigation.ts`: the gated "dealer-tasks" item, `NavGate`, and `gates` in `canSeeNavItem` and `visibleNavSections`.
- `src/components/layout/use-nav-gates.ts`: new.
- `src/components/layout/app-sidebar.tsx`, `src/components/layout/command-menu.tsx`: pass the gates.
- `src/mocks/handlers/tasks.ts`, `src/mocks/data/permissions.ts`, `src/mocks/handlers/settings.ts`: the mock.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: TASK-009.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, and the `dealer-*` and `assignee-dealers-*` screenshots in `Docs/screenshots/tasks/`.

## Tests

- `src/features/masters/components/territories-ui.test.tsx`: `findAllByText("In Gujarat")` instead of `findByText`. Every district row says it, so the test failed on `integration` (run 39074675410, issue #167) whenever several rows were already drawn.

- `src/features/tasks/components/dealer-tasks.test.tsx`, 7 tests:
  - off means 403 for a dealer;
  - assignees with dealers once the setting is on, the dealer's list, PATCH refused, and complete;
  - `link_not_visible_to_assignee`;
  - the nav item waits on its gate and the staff Tasks item stays hidden;
  - the page says it's off;
  - the page lists and completes a task with Done only;
  - New task's Dealers group.
- `src/features/tasks/api/tasks.test.ts`: the assignee shape now includes `kind` and `partner`.
- By hand, in the mock:
  1. As Admin, switch `tasks_for_dealers` on in Company settings.
  2. Give Bhavesh Shah a task.
  3. Preview as Dealer, open Tasks, and mark it done.
