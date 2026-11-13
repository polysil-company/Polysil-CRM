---
date: 2026-10-04
type: feature
title: "Tasks: meeting minutes, edit and reassign, all tasks with an Excel export"
dataIds:
  - TASK-007
  - TASK-006
  - TASK-008
  - TASK-003
  - OBS-002
author: Nakul Srivastava
breaking: false
---

## Before

PR #54 built the daily loop: My day, Team, a lead's tasks, and new, done, cancel and reopen. Three parts of the backend's tasks contract were still unused:

- `PATCH /tasks/{id}` to edit or reassign a task;
- meeting minutes (`/minutes`);
- the full task list with its filters and Excel export (`GET /tasks`, `GET /tasks/export`).

The frontend also had no way to download a file through the API client. A plain link can't carry the access token.

## Now

- **Edit or reassign** (TASK-006). An open task's menu has **Edit or reassign**. It changes what to do, the day and time, and notes, or who does it.
  - A manager can pick anyone in their team. An officer's field says only a manager can give it to someone else.
  - Only what changed is sent, with `expected_status: open`. If the task was done meanwhile, the save is refused and the list refreshes.
  - Saving shows "Task updated", or "Given to Ravi Joshi" for a reassignment.
- **Meeting minutes** (TASK-007). A **Meeting minutes** card sits on a lead's page, newest first. Each entry shows when, who was there, what was discussed, and each action item as its task stands now ("1 of 2 done", with overdue ones in red).
  - **Record minutes** from the card, or from a planned meeting's menu, which then marks that meeting done.
  - Who was there is one name per line.
  - Each action item (what, due day, for whom, kind) becomes a task. Its row on the lead then says "From meeting minutes".
  - It is one save: if the backend refuses one item, nothing is saved, and the reason appears on that item.
- **All tasks** (TASK-003, TASK-008). A third view on the Tasks page lists everything the user can see, earliest due first, with a count.
  - Filters: status, kind, person (for managers) and overdue only. All of them are kept in the URL.
  - **Download Excel** saves exactly those tasks, every page, under the name the backend gives (`tasks-2026-10-04.xlsx`).
  - More than 5,000 rows shows "Too many tasks to download — narrow the filters".
  - States: skeleton, "No tasks match these filters" with Reset, and a later page failing.
- **`apiDownload`** (OBS-002). The API client can now fetch a file. It works like any other call:
  - the access token, and one refresh and retry after a 401;
  - `x-request-id` and `x-data-id`, and the logs;
  - the backend's error envelope as an `ApiError`.

  `saveFile` saves the result. The backend's other seven list exports (`backend/docs/handover/list-exports.md`) can use the same pair.

- **"Given by you"** replaces the user's own name on tasks they gave.

## Discussion

- **Edit only what changed.** The form compares against the task as loaded, and sends a PATCH only when something differs. Closing an unchanged form sends nothing. This keeps a save from overwriting a field someone else changed meanwhile.
- **Minutes from a planned meeting.** Recording minutes from a planned meeting sends `task_id`, so the backend completes that meeting with "Minutes recorded". From the card it records a meeting that wasn't planned.
- **Field errors on action items.** The backend's `fields.action_items.1.assigned_to` paths are mapped to the matching item's field, so the reason sits where the mistake is.
- **The blob is checked by shape, not `instanceof`.** A Blob from `fetch` can belong to another realm, as with Node's fetch under jsdom, and then fails `instanceof Blob`.
- **The mock's export file.** The mock returns a stand-in file with the real headers. The real workbook comes from the backend.
- **The mock seeds one set of minutes** on the earliest done meeting about a lead, with one action item done and one open, so the card has something to show in a demo.

## Files changed

- `src/lib/api/client.ts`: `apiDownload`, `DownloadedFile`, `DOWNLOAD_TIMEOUT_MS`; the request runner is shared by JSON calls and files.
- `src/lib/api/save-file.ts`: new, saves a downloaded file.
- `src/lib/api/client.test.ts`: `[OBS-002] apiDownload`.
- `src/lib/format/date.ts`, `index.ts`, `format.test.ts`: `calendarDayOf` and `timeOfDayOf`, for date and time inputs in India's time.
- `src/features/tasks/api/`:
  - `tasks.schemas.ts`: list filters, `leadTaskParams`, the PATCH request, and the minutes schemas and requests;
  - `tasks.api.ts`: `patchTask`, `listLeadMinutes`, `createMinutes`, `exportTasks`, and the list filters;
  - `tasks.queries.ts`, `tasks.mutations.ts`, `tasks.test.ts`.
- `src/features/tasks/hooks/use-task-params.ts`: the All view and its filters in the URL.
- `src/features/tasks/components/`:
  - new: `all-tasks.tsx`, `edit-task-dialog.tsx`, `minutes-dialog.tsx`, `lead-minutes.tsx`, `task-dialogs.tsx`;
  - changed: `task-row.tsx` (Edit and Record minutes in the menu, "From meeting minutes", "Given by you"), `task-action-dialog.tsx`, `tasks-view.tsx`, `lead-tasks.tsx`, `tasks-ui.test.tsx`.
- `src/features/leads/components/lead-detail.tsx`: the Meeting minutes card.
- `src/mocks/handlers/tasks.ts`: list filters, `GET /tasks/export`, `PATCH /tasks/{id}`, and `GET`/`POST /minutes`, following the backend's rules.
- `src/mocks/data/tasks.ts`, `src/mocks/db.ts`: the seeded minutes, and plain outcomes for office tasks.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`, `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/tasks/`: the records.

## Tests

- **`src/lib/api/client.test.ts` (`[OBS-002] apiDownload`):**
  - the file, its name, the token, the Data ID and the query;
  - no name;
  - an error envelope read as an `ApiError`.
- **`src/features/tasks/api/tasks.test.ts`:**
  - `[TASK-003]`: filters by person, kind, status and overdue.
  - `[TASK-006]`: only the sent fields change and the task is reassigned; a task no longer open is refused with 409.
  - `[TASK-007]`:
    - seeded minutes with their action items as they stand;
    - recording minutes: action items become tasks, and the meeting is marked done;
    - one bad action item refuses the whole save, with its field path.
  - `[TASK-008]`: the same filters are sent with no cursor, the file is named by the backend, and an export that is too large is explained.
- **`src/features/tasks/components/tasks-ui.test.tsx`:**
  - `[TASK-006]`: rename and reassign.
  - `[TASK-007]`: the card's "1 of 2 done"; recording with validation, attendees and an action item.
  - `[TASK-008]`: overdue filter in the URL, then a download with the same filters; nothing matching, then Reset.
  - My day: a task someone else gave offers editing, not cancelling.
- **`src/lib/format/format.test.ts`:** an instant's day and time in India.
- **By hand, in Chromium on the mock backend:**
  - All tasks, a downloaded file named `tasks-2026-10-04.xlsx`, Edit, a lead's minutes and Record minutes, on a desktop in light mode;
  - All tasks on a phone in dark mode;
  - axe found nothing on All tasks, Edit or Record minutes.
