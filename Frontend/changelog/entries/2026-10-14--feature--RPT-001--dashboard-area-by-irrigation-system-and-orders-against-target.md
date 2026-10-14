---
date: 2026-10-14
type: feature
title: "Dashboard: area by irrigation system, and orders against target"
dataIds:
  - RPT-001
author: Nakul Srivastava
breaking: false
---

## Before

The backend's `GET /dashboard/overview` gained two fields with FS-052 (`dashboard.md`, "Five small changes" in `dealer-recruitment-and-small-changes.md`):

- `area_by_system`: open and won leads now, by irrigation system, with their land in hectares;
- `targets_by_month`: this month and the five before it, the order value target against what was sold, or `null` without a targets permission.

The dashboard read neither. The mock sent neither, and the frontend knew no `targets` permission.

## Now

- **Area by irrigation system,** a new dashboard card.
  - One row per system, most land first: its name, "38.5 hectares" and "14 leads", over a bar of the land.
  - "No open or won leads yet." when there are none. "None of these leads has its land recorded yet." when every system's land is zero.
- **Orders against target,** a new dashboard card.
  - One row per month, oldest first; the current month is marked "so far".
  - Each row: a bar of what was sold, a line across it at the target, and "₹9.84 L of ₹12 L 82%" beside it.
  - A key names the bar (Sold) and the line (Target), so neither rests on colour.
  - A month without a target says "no target". A role that can't see sales orders (`achieved: null`) sees "Target ₹12 L" and a description to match.
  - "No targets set for the last six months." when there is nothing to draw.
- **Left out without a targets permission.** The backend sends `null` to Accounts, Dispatch, QA and partner users, and the card is not drawn. The area card then takes the row, its rows spread over columns.
- **An older backend** without either field reads as no areas and no targets card, not as a broken contract. A month that isn't `YYYY-MM` is a contract violation.
- **`ProportionBar` takes a `marker`:** a line at a value on the bar's own scale, with a ring in the card's colour where it crosses the fill. It has stories now.
- **`formatMonth`:** "2026-10" reads "Oct 2026", in India's time.
- **The `targets` permission module,** and the mock's grants as migration 035 seeds them: officers view their own, managers view and set their team's, Admin everything.
- Checked on a desktop in light mode and a phone in dark mode as a State Manager, as Accounts (no targets) and as a field officer in dark mode. axe found nothing.

## Discussion

- **Rows, not a column chart.** Both cards follow the dashboard's existing pipeline and sources cards: a label, the figures in text, and a thin bar. Every value is printed beside its bar, so there is no hover tooltip to find and nothing is lost on a phone.
- **One hue.** The bars are the primary colour; the target line is the text colour with a ring. No status colour marks a month over or under target: the percentage says it.
- **One scale per card.** The targets bars share the largest of every target and sale, so months compare with each other, and a month over target runs past its line.
- **Sorted by land** rather than the backend's name order, so the comparison reads at a glance.
- **Not yet checked on staging.**

## Files changed

- `src/features/dashboard/api/dashboard.schemas.ts`: `area_by_system` and `targets_by_month`, read as `areaBySystem` (default `[]`) and `targetsByMonth` (default `null`); `amount`.
- `src/features/dashboard/components/dashboard-charts.tsx`: new, `AreaBySystemCard`, `TargetsCard` and their skeleton.
- `src/features/dashboard/components/dashboard-overview.tsx`: the new row, and its skeleton.
- `src/components/patterns/proportion-bar.tsx`, `proportion-bar.stories.tsx`: the `marker`; stories.
- `src/lib/format/date.ts`, `index.ts`: `formatMonth`.
- `src/lib/auth/permissions.ts`, `src/mocks/data/permissions.ts`: the `targets` module and its grants.
- `src/mocks/handlers/dashboard.ts`: both fields, with `null` targets for a role without them.
- `src/lib/data-ids/registry.ts`: RPT-001's title and note.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/dashboard/`: records and screens.

## Tests

- `src/features/dashboard/api/dashboard.test.ts`, `[RPT-001] getDashboardOverview`:
  - both fields read from the backend's shape;
  - an older backend without them: no areas, no targets;
  - a month that isn't `YYYY-MM` refused;
  - the mock sends six months to a manager and `null` to Accounts.
- `src/features/dashboard/components/dashboard-charts.test.tsx`:
  - `[RPT-001] AreaBySystemCard`: most land first, hectares and leads; the empty and no-land notes;
  - `[RPT-001] TargetsCard`: sold of target with its share, "so far", the key; targets alone; no targets;
  - `[RPT-001] DashboardOverview charts`: both cards for a manager; no targets card for Accounts.
- `src/lib/format/format.test.ts`: `formatMonth`.
- Walked through in the mock: desktop light and phone dark as a State Manager, desktop as Accounts, desktop dark as a field officer.
