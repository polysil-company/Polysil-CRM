---
date: 2026-10-18
type: feature
title: Holidays, and complaint escalation
dataIds:
  - CMPL-012
  - MSTR-019
author: Nakul Srivastava
breaking: false
---

## Before

Complaint targets skipped Sundays but no holidays, and nobody could set any. A complaint that missed a target showed only "Late", and nothing told its owner or managers.

## Now

Built to `complaint-holidays-escalation.md` (FS-028).

**Masters → Holidays (MSTR-019)**

- Shows a year's holidays: name and weekday date, with a year switcher.
- Those who edit masters can **Add holiday**: a day from tomorrow on, not a Sunday, and a name.
- A holiday still ahead can be removed after confirming. A past one shows "Past" and stays.
- `holiday_in_past`, `holiday_sunday` and `holiday_exists` show on the day field.
- The note "A new holiday applies to complaints submitted after it is added." sits under the list.
- Loading, empty, error, read-only, phone and dark states are covered.

**Escalation (CMPL-012)**

- While the **Complaint escalation** setting is "Ring the bell", a complaint that misses a target says so:
  - by its status, **Response target missed** or **Resolution target missed**, in place of "Late";
  - on its Targets card, "Escalated to its owner and managers" with the time.
- Its history reads "Response target missed: escalated" (or Resolution), by no one, with when it was due.
- The bell gains the `complaint_escalated` kind, with an alarm-clock icon, opening the complaint.
- The fields are staff only; a dealer always reads null.
- The setting was already on Company settings.

**Mock**

- Seeds sample holidays for 2026–27 and serves the three endpoints with their refusals.
- Escalates complaints past their targets while the setting is on, with their history events.
- Adds one read escalation to the bell.
- Generates complaints before notifications, so the notification can name one.

The Masters subtitle now lists warranty periods and holidays.

Walked in the mock as Admin on a desktop in light mode, and on a phone in dark mode. Axe found nothing, with no console errors and no sideways scroll.

## Discussion

- A past holiday can't be removed and only future ones can be added, because targets already counted with a day must not move (contract). The panel shows only what may change.
- "Target missed" replaces "Late" only when the backend says it escalated; otherwise "Late" stays as before.

## Files changed

- Holidays:
  - `src/features/masters/api/holidays.{schemas,api,queries,mutations}.ts`: new.
  - `src/features/masters/components/holidays-panel.tsx`: new, with `holidayProblems` and `holidayRefusal`.
  - `src/features/masters/components/masters.tsx`: the Holidays tab.
  - `src/components/layout/navigation.ts`: the Masters subtitle.
- Escalation:
  - `src/features/complaints/api/complaints.schemas.ts`: `response_escalated_at` and `resolution_escalated_at`.
  - `src/features/complaints/components/complaint-detail.tsx`: the badges and the Targets card line.
  - `src/features/complaints/lib/complaint-labels.ts`: `complaint.escalated`.
  - `src/features/notifications/api/notifications.schemas.ts`, `src/features/notifications/components/notification-bell.tsx`: the `complaint_escalated` kind and its icon.
- Mock:
  - `src/mocks/data/holidays.ts` and `src/mocks/handlers/holidays.ts`: new.
  - `src/mocks/handlers/complaints.ts`, `src/mocks/data/notifications.ts`, `src/mocks/db.ts`, `src/mocks/handlers/index.ts`: escalation, the bell sample, the holidays table and the new handlers.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: MSTR-019 and CMPL-012.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/masters/*holiday*`, `Docs/screenshots/complaints/*escalated*`.

## Tests

- `src/features/complaints/components/complaints-escalation.test.tsx`, 6 tests:
  - `holidayProblems`;
  - the holiday contract: a year, add, `holiday_exists`, `holiday_in_past`, `holiday_sunday`, remove, a past one kept, `forbidden`;
  - the panel: lists, Past without remove, adds one;
  - escalation on, and off by the setting;
  - the history line;
  - the badge and Targets card line on the complaint.
- `src/features/complaints/api/complaints.test.ts`: a seeded complaint past its target now also carries the escalation event.
- To check by hand in the mock as Admin:
  1. Open Masters → Holidays and add a day.
  2. Open complaint Poly/Comp./2026-27/GJ/01 and check the missed-target badge.
  3. Open the bell and find the escalation.
