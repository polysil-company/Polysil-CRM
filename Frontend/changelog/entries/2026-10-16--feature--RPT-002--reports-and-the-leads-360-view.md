---
date: 2026-10-16
type: feature
title: Reports, and a lead's 360° view
dataIds:
  - RPT-002
  - RPT-003
author: Nakul Srivastava
breaking: false
---

## Before

The backend serves eight reports for managers and HQ, and a 360° view of a lead (handover `reports-contract.md`, FS-024; `when-a-sale-counts.md`, FS-026). "Reports" sat in the menu marked Soon, and a lead's page had no summary across its quotations, orders, money, complaints, visits and tasks.

## Now

- **Admin → Reports** (`/reports`): a card for each report the user may open, with its figure over the last 30 days.
  - The reports: lead conversion, salesperson performance, lost leads, follow-ups, dealer performance, campaign performance, territory performance and complaints.
  - Each card is the report's link. A report that answers 403 is left out, as the handover asks. With none left, the page says there are no reports for your role.
- **Each report** (`/reports/{name}`):
  - **Filters**, each only where the report takes it, and all in the URL so a report can be bookmarked or shared:
    - From and to (empty means the backend's last 30 days);
    - Area (the leads list's area picker, up to 20);
    - Person (you and the staff below you);
    - By: source, person or territory; reason or person; type, status or severity; district or taluka.
  - **What the figures used:** the window, or "As of" for follow-ups, and "Sales counted at: approval" on the reports that count sales (`data.filters.sale_counted_at`).
  - **A table with a Total line** where the backend sends totals. On a phone the secondary columns step aside, so nothing scrolls sideways.
  - **A figure the user may not see** comes as null, never 0. It shows as a dash, read out as "Not available to you", with a line under the table saying so.
  - **Before asking:** a window over a year, or one that ends before it starts, is named instead of sent.
  - **Past 1,000 rows** a notice says only the first are shown, and that the totals count them all.
  - **A 403** says the role can't run the report.
  - **Download Excel** asks for the same report with `format=xlsx`.
- **At a glance on a lead** (RPT-003), for staff who see reports:
  - Seven tiles: quotations, orders (with their value), received, complaints, visits, open tasks and the subsidy stage.
  - Then the other leads on the same mobile, each linked with its stage. The handover asks for "same mobile", never "same customer", because farmers share phones.
  - The timeline below stays the lead's own.
- Admin's menu item now opens Reports, with a description.
- Checked on a phone in dark mode and a desktop in light mode, as Admin and as a State Manager. axe found nothing.

## Discussion

- **Eight reports, not seven.** The handover's table lists seven. The backend also serves campaign performance (FS-040), so it's here too. Campaigns themselves come with item 27.
- **Shapes from the backend's code.** Each report's rows and totals follow `api/services/reports.py`, including where it differs from the handover's example:
  - follow-ups' filters are `{as_of, owner_id}`;
  - territory performance takes `level`, not `group_by`;
  - an "Above this level" row has a null territory;
  - complaints' totals carry the refunds.
- **Subsidy stage null has two meanings.** On the 360° view it means either "not yours to see" or "no application". The tile shows a dash without the subsidy permission, and "None" with it.
- **A status or severity row** comes with its code as its label. The complaints report shows the complaint screens' words for it.
- **The mock counts from its own data**, so the filters change the figures. Where it has nothing to count, it says so in `src/mocks/handlers/reports.ts`:
  - Payments, visits and campaign costs belong to modules the mock grants only Admin, so other roles see dashes.
  - Leads carry no stage dates, so a lead is won or lost on its last activity.
  - Complaints carry no submitted date, so the complaints report ignores the window.
  - Three seeded campaigns stand in.
  - The sale setting reads as "approval".
- **Not done here:** clicking a figure through to the list behind it. The backend has no drill-down links yet.

## Files changed

- `src/features/reports/` — new:
  - `api/`: the contract for the eight reports and the 360° view, the calls (one typed fetcher per report) and the query options.
  - `lib/report-catalogue.ts`: each report's title, description and filters.
  - `components/`: `reports-home.tsx`, `report-view.tsx` (filters), `report-bodies.tsx` (the eight tables), `report-table.tsx` and `lead-360.tsx`, with tests.
- `src/app/(app)/reports/page.tsx`, `src/app/(app)/reports/[report]/page.tsx` — new: the routes. An unknown report is a 404.
- `src/features/leads/components/lead-detail.tsx` — At a glance, above Details.
- `src/components/layout/navigation.ts` — Reports opens `/reports`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — RPT-002 filled in; RPT-003 for the 360° view.
- `src/mocks/handlers/reports.ts` — new: the eight reports and the 360° view, with the backend's 403s and 422s. Also `handlers/index.ts`.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/reports/` — records and screens.

## Tests

- `src/features/reports/components/reports.test.tsx`:
  - `[RPT-002]` through the API:
    - conversion by source and by person, with the same total;
    - a bad grouping and a backwards window refused;
    - a withheld figure null for a State Manager and a number for Admin;
    - an Employee and a QC Manager refused;
    - the Excel file named as the backend names it.
  - `[RPT-003]` through the API: the leads on the same mobile, and an Employee refused.
  - Home: cards with figures for a District Manager; "No reports for your role" for an Employee.
  - A report:
    - the table, its Total line, and regrouping by person;
    - dashes, their line, and the sale setting;
    - a window over a year stopped before asking;
    - a refused report.
  - At a glance: tiles, a withheld figure, the same-mobile lead linked; nothing for an Employee.
- Walked through in the mock:
  - every report;
  - the home page on a desktop and on a phone in dark mode;
  - a lead's 360° view on both.
