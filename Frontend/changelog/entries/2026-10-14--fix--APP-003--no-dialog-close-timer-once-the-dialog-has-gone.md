---
date: 2026-10-14
type: fix
title: No dialog close timer once the dialog has gone
dataIds:
  - APP-003
author: Nakul Srivastava
breaking: false
---

## Before

After a save, eleven dialogs show "Saved" and close themselves 600 ms later:

- leads: assign, stage, new lead;
- orders: every action;
- quotations;
- complaints;
- tasks: new, edit, action, minutes;
- approval limits.

Each cleared its timer when it went away, but none checked whether it had gone before starting one. `useAsyncAction` runs a success handler even after its component has unmounted, on purpose, so that the toast still shows. So a save that finished after the dialog was closed, or after the user left the page, started a timer that nothing would ever clear. It then closed a dialog that no longer existed.

In the browser this did nothing visible. In the unit tests, a timer could outlive its test file. On 13 October, CI on PR #124 failed after all 1010 tests had passed, with "ReferenceError: window is not defined" from the lead assign dialog's timer, firing after jsdom was torn down (`lead-assign.test.tsx`).

## Now

- **One hook,** `useCloseAfterSuccess` in `src/hooks/`, closes a dialog a moment after a save:
  - its timer is cleared when the dialog goes;
  - it is never started once the dialog has gone.
- **Nine dialogs use it.** Their own copies are gone: three local hooks, the complaints' `useCloseLater`, and five inline timers.
- **The new-lead and new-task dialogs** also reset their form when they close. They keep their own timer, with the same never-after-it-has-gone guard.
- Nothing changes on screen.

## Discussion

- **Why the timers and not `useAsyncAction`.** Not calling `onSuccess` after unmount would also stop the leak. But it would lose the toast, and the page change after a delete, when the user had closed the dialog mid-save. The timer is the only part that must not outlive the dialog.
- **Ported into PR #124,** whose CI it failed. The change is identical there, so it merges cleanly whichever lands first. Any other open PR picks it up from `integration`.

## Files changed

- `src/hooks/use-close-after-success.ts`: new, the hook and `CLOSE_AFTER_SUCCESS_MS`.
- **Using the hook:**
  - `src/features/orders/components/order-dialog-shared.tsx`, `order-action-dialog.tsx`, `record-dispatch-form.tsx`;
  - `src/features/leads/components/lead-assign-dialog.tsx`, `lead-stage-dialog.tsx`;
  - `src/features/quotations/components/quotation-action-dialog.tsx`;
  - `src/features/complaints/components/complaint-dialog-parts.tsx`, `complaint-actions.tsx`, `complaint-targets.tsx`, `remedy-card.tsx`;
  - `src/features/tasks/components/edit-task-dialog.tsx`, `minutes-dialog.tsx`, `task-action-dialog.tsx`;
  - `src/features/approvals/components/approval-limit-dialog.tsx`.
- **Guarded in place:** `src/features/leads/components/new-lead-dialog.tsx`, `src/features/tasks/components/new-task-dialog.tsx`.

## Tests

- `src/hooks/use-close-after-success.test.ts`, `[APP-003] useCloseAfterSuccess`:
  - closes after the moment;
  - forgets the close when the dialog goes first;
  - starts no timer when a save finishes after the dialog has gone (the case CI hit).
- The dialogs' own tests pass unchanged: leads, orders, quotations, complaints, tasks and approvals, 272 tests.
