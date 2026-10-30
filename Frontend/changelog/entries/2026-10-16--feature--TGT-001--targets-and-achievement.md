---
date: 2026-10-16
type: feature
title: Targets and achievement
dataIds:
  - TGT-001
  - TGT-002
author: Nakul Srivastava
breaking: false
---

## Before

The backend keeps monthly targets per person on four measures: order value, orders, leads won and visits. It also works out achievement live (handover `targets-contract.md`, FS-025). The frontend had no screen for either. Nobody could see their month against a target, and managers couldn't set one.

## Now

- **Sales → Targets** (`/targets`), for staff who hold `targets`.
- **The month** is in the URL. It moves a month at a time, with **This month** to come back. A line says when the figures were taken and when a sale counts ("Sales counted at: approval").
- **Your month:** four cards, one per measure. Each shows what you've achieved so far against its target, with the share and a bar, or "No target set". A measure your role may not see is a dash, read out as "Not available to you".
- **Your team:** a card for each person below you, with or without a target, then **All together**.
  - A field officer sees only their own month.
  - An administrator carries no targets, so they see everyone and have no month of their own.
- **Set targets**, for those who may set them (TGT-002), opens a dialog:
  - **The fields:** the four measures as they stand, then the changes to them this month, newest first, each with who made it.
  - **Saving** sends only what changed. Emptying a measure sends 0, which clears it, and the field says so before saving.
  - **Checks before sending:** a count that isn't a whole number, or rupees with more than two decimal places, is named on its field.
  - **Refusals in words:** `not_your_team`, `month_closed`, `user_inactive` and `no_targets`. Field errors show on their measure.
  - **A past month** warns first that only an administrator changes it.
  - **After saving**, achievement refreshes.
- Checked on a phone in dark mode and a desktop in light mode, as a State Manager and as a Field Officer. axe found nothing.

## Discussion

- **A new module code, `targets`.** The backend gates these endpoints with it (`require("targets", …)`), so it joins the frontend's module list. The mock grants it as follows:
  - field officers: view, own;
  - managers: view and create, over their team;
  - administrators: everything.
- **The backend's code, where the handover is silent:**
  - `achievement` also answers `filters.sale_counted_at`;
  - order value is a decimal string and the other measures are whole numbers;
  - a past month is closed except at global scope (GAP-233), and twelve months ahead is the limit;
  - a setter's name can be blank for someone without `users.view`, so the history then leaves out "by".
- **A target of 0 reads as "No target set".** The backend keeps 0 as the value that clears a target, and sends no share for it.
- **Cards, not a table.** Each person shows four measures with a bar each. A table of sixteen figures doesn't fit a phone, and cards keep every measure in view at 360 px.
- **`formatMonth` and `shiftMonth`** join `src/lib/format`, since dates are formatted only there.
- **The mock** counts orders approved in the month and leads won in it, by owner. Leads carry no won date in the mock, so a lead counts in the month of its last activity. Visits are visible only to Admin. Most of the team has targets seeded for this month and the last.

## Files changed

- `src/features/targets/` — new:
  - the contract, calls, queries and mutation;
  - the measure labels;
  - the `TargetsView` page and the `SetTargetsDialog`, with tests.
- `src/app/(app)/targets/page.tsx` — new: the route.
- `src/components/layout/navigation.ts` — Targets in the Sales menu.
- `src/lib/auth/permissions.ts` — the `targets` module.
- `src/lib/format/date.ts`, `index.ts`, `format.test.ts` — `formatMonth` and `shiftMonth`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — the TGT domain; TGT-001 and TGT-002.
- `src/mocks/data/permissions.ts`, `src/mocks/data/targets.ts` (new), `src/mocks/db.ts`, `src/mocks/handlers/targets.ts` (new), `handlers/index.ts` — the grants, seeded targets, and the three endpoints with the backend's rules.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/targets/` — records and screens.

## Tests

- `src/features/targets/components/targets.test.tsx`:
  - `[TGT-001]` through the API: a field officer's single row with visits withheld; a manager with the team below; a dealer refused.
  - `[TGT-002]` through the API:
    - a teammate's targets set, with their history;
    - your own refused (`not_your_team`);
    - a past month refused for a manager (`month_closed`) but taken from Admin;
    - a fractional count refused on its field;
    - a field officer refused.
  - The page:
    - a field officer's month, with nothing to set;
    - moving a month and back.
  - The dialog:
    - a bad count named;
    - only the changes saved, with an emptied target cleared;
    - a past month's warning and its refusal.
- `src/lib/format/format.test.ts`: `shiftMonth` across a year, and `formatMonth`.
- Walked through in the mock:
  - the team on a desktop and on a phone;
  - a field officer's month;
  - setting targets and saving;
  - a past month on a phone in dark mode.
