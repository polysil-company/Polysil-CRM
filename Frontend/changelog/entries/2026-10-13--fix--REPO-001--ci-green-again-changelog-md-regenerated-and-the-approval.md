---
date: 2026-10-13
type: fix
title: "CI green again: CHANGELOG.md regenerated, and two tests that depended on timing"
dataIds:
  - REPO-001
  - QUOT-007
  - TASK-005
author: Nakul Srivastava
breaking: false
---

## Before

GitHub Actions runs again, and two checks failed on `integration` after #111 and #114:

- **"CHANGELOG.md is up to date".** The stacked PRs #112 and #113 merged into the MSTR-007 branch, and that branch then merged into `integration` (#114). The generated `CHANGELOG.md` was never rebuilt after the last merge, so `npm run changelog:build -- --check` found it stale.
- **`[QUOT-007] Ask for approval`** timed out on CI looking for "Waiting for approval". The CI output shows why: the page was still inert behind the closing dialog, and an inert page is hidden from role queries. A slow runner outlasted `findByRole`'s default second. It passes locally.
- **`[TASK-005]` refuses an officer cancelling a task someone else gave them** failed locally on 13 October. It searched the seed for an open task of the user's given by someone else. The seed settles tasks whose due time has passed, so by late morning that task was done and the search found nothing. The result depended on the hour.

## Now

- `CHANGELOG.md` is rebuilt from the entries, so the check passes.
- The approval test first waits for the dialog to close, then finds the button, each with a 5-second ceiling. It still fails at once if the button never appears or isn't disabled.
- The task test makes its own precondition: it takes an open task of the user's and gives it a manager as the one who assigned it, then expects the 403. `afterEach` resets the mock database.

## Discussion

- Nothing on screen changes; the client's app is the same.
- `npm run verify` runs `changelog:check` but not `changelog:build -- --check`, so a stale `CHANGELOG.md` only shows up on CI. Run `npm run changelog:build` after every merge into a branch, as `Docs/Frontend-Handover.md` §4.13 says.

## Files changed

- `CHANGELOG.md`: regenerated.
- `src/features/quotations/components/quotation-actions.test.tsx`: the `[QUOT-007]` test waits for the dialog to close.
- `src/features/tasks/api/tasks.test.ts`: the `[TASK-005]` test sets up its own task.

## Tests

- `npx vitest run --project unit src/features/quotations/components/quotation-actions.test.tsx`: 7 passed, three runs in a row.
- `npx vitest run --project unit src/features/tasks/api/tasks.test.ts`: 27 passed, at the hour it had failed.
- `npm run changelog:build -- --check` passes.
- `npm run verify` passes.
