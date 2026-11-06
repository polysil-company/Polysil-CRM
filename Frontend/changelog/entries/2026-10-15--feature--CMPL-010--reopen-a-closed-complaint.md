---
date: 2026-10-15
type: feature
title: "Reopen a closed complaint"
dataIds:
  - CMPL-010
author: Nakul Srivastava
breaking: false
---

## Before

The backend reopens a closed or QC-rejected complaint (`POST /complaints/{id}/reopen`, FS-036, `settings-amend-reopen-contract.md`), and its detail says when that applies (`can.reopen`) and how often it happened (`reopen_count`, `reopened_at`, `reopen_reason`). The frontend had no button for it. When the same emitters failed again after a complaint closed, someone had to raise a new complaint and lose its history.

## Now

- **Reopen** shows on a closed or QC-rejected complaint while the backend's `can.reopen` allows it. The backend decides who and until when:
  - whoever raised a closed complaint;
  - the roles in the `complaint_reopen_roles` setting (QC and Support by default), for a closed or a rejected one;
  - within `complaint_reopen_days` (30) of closing or rejection, and at most `complaint_reopen_max` (2) times.
- **The dialog** asks why. It says what follows: the manager's check, QC and a remedy again, and how often it was reopened before. Staff see the reason; a dealer doesn't.
- **After reopening**, the complaint is "Waiting for a check" again. A note says "Reopened once" (twice, N times), with the reason and when.
- **The history** shows the backend's `complaint.submitted` event with `reopened: true` as "Reopened", or "Reopened after QC rejected it", and says whether the targets start again or run on.
- **Refusals:**
  - no reason: on the field;
  - the window closed meanwhile (`422 reopen_window_closed`) or someone acted first (`409`): the dialog closes, a toast says why, and the complaint refreshes;
  - a role not allowed (`403`): "Not yours to reopen";
  - nobody to check it (`422 no_checker`): the existing message.
- **The mock** follows `complaint_reopen_refusal()` (migration 041) with the default settings. It seeds one closed complaint, with no remedy due, raised by the signed-in staff user. A reopen keeps the history so far, and the seeded history now includes the remedy and the close.
- Checked on a desktop in light mode and a phone in dark mode. axe found nothing on the closed complaint, the dialog, or the reopened complaint.

## Discussion

- **The mock's QC role is `qa_manager`;** the backend's is `qc_manager`. The mock lets `qa_manager` stand for the setting's roles.
- **The QC verdict and the last remedy stay on the page** after a reopen, as the detail sends them ("the live or the last remedy"); the new round adds its own.
- **Company settings** (the window, the cap, the roles and whether targets restart) are item 21 of the plan; until then they keep the backend's defaults.
- **Not yet checked on staging.**

## Files changed

- `src/features/complaints/api/complaints.schemas.ts`: `can.reopen`, `reopenCount`, `reopenedAt`, `reopenReason`, and the reopen request.
- `src/features/complaints/api/complaints.api.ts`, `complaints.mutations.ts`: `reopenComplaint` and `useReopenComplaint`.
- `src/features/complaints/components/complaint-actions.tsx`: the Reopen button and dialog.
- `src/features/complaints/components/complaint-detail.tsx`: the "Reopened N times" note.
- `src/features/complaints/lib/complaint-labels.ts`: `reopen_window_closed`, `timesText`, and the history line.
- `src/mocks/handlers/complaints.ts`, `src/mocks/data/complaints.ts`: the reopen route and rule, and a closed complaint.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: CMPL-010.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/complaints/reopen-*`: records and screens.

## Tests

- `src/features/complaints/components/complaints-reopen.test.tsx`:
  - the raiser reopens a closed one: a new round, counted, with the reason;
  - a reason is needed;
  - a rejected one only for the allowed roles;
  - refused once reopened as often as allowed;
  - a complaint not closed or rejected is refused as moved on;
  - the reason hidden from a dealer;
  - on the page: the empty reason, the reopen, the note and the history;
  - no Reopen on a rejected one outside the roles;
  - the window closing meanwhile closes the dialog;
  - the words: "once", "twice", "3 times", and a reopen told apart from a submit.
- Walked through in the mock: desktop light and phone dark.
