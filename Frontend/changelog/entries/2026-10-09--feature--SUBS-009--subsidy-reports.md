---
date: 2026-10-09
type: feature
title: Subsidy reports
dataIds:
  - SUBS-009
  - SUBS-010
  - SUBS-011
author: Nakul Srivastava
breaking: false
---

## Before

Applications could be worked one at a time (#78), but no report showed the state of the business. The backend serves the client's three reports (FS-009a, handover `subsidy-reports-and-masters.md`), each with an Excel export:

- the six ageing figures per application;
- the stage dashboard;
- supply by district.

## Now

- **Subsidy → Reports**, a third tab, with three reports (`?report=`):
  - **Stages:**
    - one row per stage holding an application, in order;
    - applications, total cost, subsidy, farmer share, and the oldest's days in the stage;
    - a total row;
    - for one status at a time, open by default.
  - **Supply:**
    - supplied and not supplied by district, with their cost and a total row;
    - cancelled applications are left out unless chosen.
  - **Ageing:** each application's six figures, newest first. A step with no end counts to today and says "running". A dash means its start isn't recorded. Filters: status, stage and search, with Show more.
- Each report downloads as Excel with its filters.
- On a phone, the cost columns step aside so the tables fit, and each ageing card lays its figures out two by two. Checked at 360 px in dark mode.

## Discussion

**Decisions:**

- **Ageing is cards, not a wide table.** Six figures and an application don't fit a phone as columns. Each card reads on its own, and shows three or six figures to a row on wider screens.
- **No "every status" on the stage report.** The backend's `status` defaults to open and can't be emptied, so the filter offers one status at a time, and clearing it returns to open.
- **Totals are added with `sumRupees`,** in whole paise, never through floating point. The totals are the screen's own, labelled "All stages" and "All districts". Neither the export nor the backend sends them.
- **Phone tables leave out columns rather than scroll.** A sideways-scrolling box with nothing to focus fails axe (`scrollable-region-focusable`). The cost columns stay on the desktop and in the export.

**The mock:**

- The mock works the reports out from its applications with the backend's rules. Each figure runs from a recorded start to its end, or to today, or to the day it was cancelled. "Supplied" means stage 7's supply date is in.
- The seeded applications now record a date at each stage they passed (submission, supply, WO, TPA, inspection, TR, FP), so the reports have figures to show.

## Files changed

- `src/features/subsidy/`:
  - `api/subsidy-reports.{schemas,api,queries}.ts`, with `subsidy-reports.test.ts`;
  - `components/subsidy-reports.tsx` and `subsidy-reports.test.tsx`;
  - `components/subsidy-tabs.tsx`: the Reports tab.
- `src/app/(app)/subsidy/reports/page.tsx`: the route.
- `src/mocks/handlers/subsidy-reports.ts`: new. `handlers/subsidy-applications.ts`: seeded stage dates, and its store exported. The handler list.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SUBS-009…011.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/subsidy/`: the records.

## Tests

**`src/features/subsidy/api/subsidy-reports.test.ts`:**

- `[SUBS-009]`:
  - six figures per application; a supply date with no full payment runs from today;
  - a status filter;
  - a dealer gets 403.
- `[SUBS-010]`: open applications counted by stage in stage order, with money.
- `[SUBS-011]`: supplied and not supplied add up to every application that isn't cancelled.

**`src/features/subsidy/components/subsidy-reports.test.tsx`:**

- the stage report with its total row;
- the supply report;
- the ageing cards with their labels and "running".

**By hand, in Chromium on the mock backend, as a State Manager:**

1. The three reports on a desktop, and the ageing download.
2. Ageing and stages on a 360 px phone in dark mode.

axe found nothing on any of these.
