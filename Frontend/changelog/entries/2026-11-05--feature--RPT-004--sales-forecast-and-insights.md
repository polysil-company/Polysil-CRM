---
date: 2026-11-05
type: feature
title: Sales forecast and insights
dataIds:
  - RPT-004
  - RPT-005
author: Claude
breaking: false
---

## Before

- The backend's FS-079 added two reports:
  - `GET /reports/sales-forecast`: what the open pipeline is likely to bring in, and roughly when, from each stage's win rate;
  - `GET /reports/insights`: plain sentences about the period against the one before.
- The frontend's reports listed only the eight from PR #149.

## Now

- **Two more reports**, with cards on the reports home and pages of their own.
- **Sales forecast** (`/reports/sales-forecast`):
  - **"Likely"** is the open pipeline weighted by each stage's win rate, beside the open pipeline, open leads (and how many have a value), and the typical time to win.
  - **A table** by person (the backend's default), territory or source: open leads, pipeline, likely, and likely by this month, the next two, and later.
  - **"Win rates used"** lists each stage's rate. A stage that borrowed an earlier stage's rate is marked "(borrowed)" and explained. The rates come from everything the user may see, while the filters only choose the rows, as the backend says.
  - **With too little history**, a notice says the pipeline can't be weighed yet, and every likely figure is a dash. Never ₹0.
  - **Filters:** area and person, in the address, and the same Excel file as every report.
- **Insights** (`/reports/insights`):
  - each sentence with its figure ("42.5%", "6 hours") and what it was before;
  - **See the report** opens the report behind it, with its grouping ("Lost leads, by reason");
  - the window and the one it is compared with;
  - nothing to say reads "Too little happened in this window to say anything", because a missing sentence means thin data, not a problem.
- **The home cards:**
  - the forecast's is "₹4.2 L likely, of ₹9.8 L open, across 23 leads" (or the open pipeline alone, with too little history);
  - the insights card is how many there are, with the first sentence under it.

## Discussion

- **Their own shapes.** Neither answers rows, totals and filters like the other eight: the forecast's filters carry a date, not a moment, and insights have no totals. So they keep the reports' list, page, filters and refusals, but each has its own frame. The shared frame is now typed to the eight table reports only.
- **The months** are the backend's (`months`, then `later`), shown as "Nov 2026", "Dec 2026", "Jan 2027", "Later". On a phone the month and pipeline columns are left out, so the table fits; the likely figure stays.
- **`history_days`** (90 to 365, 180 by default) isn't offered yet; the page says which period the rates used.
- **The mock:**
  - the forecast takes its own simple rates (the overall win rate, scaled along the stages) and months by stage;
  - insights gives up to three sentences from the mock's leads.
  - The backend's arithmetic (`api/domain/forecast.py`, `insights.py`) is the real one.

## Files changed

- `src/features/reports/api/reports.schemas.ts`, `reports.api.ts`: the two reports, and `TableReportName`.
- `src/features/reports/components/report-bodies.tsx`: their frame and bodies.
- `src/features/reports/components/reports-home.tsx`: their home cards.
- `src/features/reports/lib/report-catalogue.ts`: their titles, descriptions and filters.
- `src/mocks/handlers/reports.ts`: both reports.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: RPT-004 and RPT-005.
- `Docs/Plan.md` §9.1, `Docs/plan-13oct-2026.md`, `Docs/Tested-Features.md`, `Docs/screenshots/reports/`: records and screens.

## Tests

- **`[RPT-004] The sales forecast`:**
  - the pipeline by month with its rates, the same total by territory;
  - the table, the likely total and the win rates on the page;
  - too little history shows the notice and dashes, not ₹0.
- **`[RPT-005] Insights`:** each sentence with its figure, what it was, and its report's link; the empty answer said in words.
- The existing report tests pass.
