---
date: 2026-10-10
type: feature
title: Subsidy masters and state schemes
dataIds:
  - SUBS-012
  - SUBS-013
  - SUBS-014
author: Nakul Srivastava
breaking: false
---

## Before

Every subsidy calculation reads the scheme's masters: categories, parameters, component rates, crop spacings, and the unit-cost and quantity matrices. Only the backend's seed could change them. Since migration 044 each state has its own scheme (FS-039, handover `subsidy-schemes-contract.md`). A new state's scheme starts empty and can't calculate until an administrator fills it, and nothing on screen did that.

## Now

- **Admin → Subsidy masters** (`/subsidy-masters`, staff with `masters`), one scheme at a time:
  - a **Scheme** picker (`?scheme=`, GGRC by default) and an **In force on** date (`?on=`, today by default) to see the figures that applied on any day;
  - seven tabs (`?table=`): Overview, Categories, Parameters, Component rates, Crop spacings, Unit costs, Quantities.
- **Overview (SUBS-014):**
  - the scheme's name, code, state, number of applications, and a Ready / Not ready / Switched off badge;
  - one card per system: "Can calculate", or each thing a calculation would still refuse on, in the engine's order, each with an **Open** button to the tab that fills it;
  - its stages in order, each with **Rename**;
  - **Switch off / Switch on**, after a confirm that says what happens to its applications;
  - **New scheme:** code, name, state, the scheme to start from, and the systems to run. It copies the template's settings and stages, never its figures;
  - while an active scheme has no state, a banner asks for it to be linked first, with a **Link to a state** dialog, and New scheme stays off.
- **Tables (SUBS-012):** the rows in force on the date. **Revise from a date** edits any figure. Only changed rows are sent, from today or a later date. **Add rows from a date** fills an empty table, as a new scheme needs. Choices (system, variant, unit, nozzle) are pickers. A refusal on one row lands on that row.
- **Matrices (SUBS-013):** each matrix in force as a grid, with **Copy as grid** for Excel. **New matrix** starts from blank or from the one in force: paste the grid back from Excel, and every bad cell is named by row and column.
- **The calculator** gets a **Scheme** picker (`?scheme=`) once more than one scheme is active. Each scheme shows only its own systems.
- On a phone everything stacks. Checked at 360 px in dark mode with no sideways scroll.

## Discussion

**Decisions:**

- **Overview first.** A new scheme is mostly a to-do list. Opening on what's missing, each item one click from its table, beats making the administrator guess which of six tables is short.
- **The masters screen holds the schemes,** rather than a separate schemes page. Each scheme's figures are its masters, so one picker serves both, and the handover's three screens (list, new, detail) fit as a picker, a dialog and the Overview tab.
- **Missing items are named in words,** with the backend's key kept where it is the table's own name (`parameters:insurance_rate` reads "The insurance_rate parameter", as the Parameters tab lists it). An item the screen doesn't know shows as sent, with no link. `stages` says "contact support", as the handover asks.
- **Refusals land on fields:** `code_taken` on Code, `state_has_scheme` on State, 422 `fields` on their inputs. The rest show above the buttons.
- **No invented rules.** Which states may take a scheme, and when a scheme is ready, are the backend's answers. The form checks only the code's shape and that fields are filled.

**The mock:**

- It follows migration 044:
  - GGRC is linked to Gujarat, as the backfill does;
  - a second state, Uttar Pradesh, sits after every other territory, so no existing id moves;
  - one active scheme per state, a state set only once, and legacy mode never mixing with linked schemes;
  - `for-lead` finds the lead's state's scheme, falling back to the one active scheme only in legacy mode.
- The masters are kept per scheme, and a new scheme's start empty.
- Readiness follows the engine's order. Its required parameters, quantity rows and rates are GGRC's.
- The calculator's endpoints take `scheme`:
  - an inactive or unknown scheme is a 422 on `scheme`;
  - a scheme that lacks a table is a 404, as the engine answers.
- A renamed stage shows in that scheme's stage list.

## Files changed

- `src/features/subsidy/`:
  - `api/subsidy-masters.{schemas,api,queries,mutations}.ts` and `api/subsidy-schemes.{schemas,api,queries,mutations}.ts`, with `api/subsidy-masters.test.ts`;
  - `lib/master-revision.ts`, `lib/matrix-grid.ts`, `lib/scheme-readiness.ts`, with `lib/subsidy-masters-lib.test.ts`;
  - `components/subsidy-masters.tsx`, `master-configs.tsx`, `master-panel.tsx`, `matrix-panel.tsx`, `scheme-overview.tsx`, with `subsidy-masters.test.tsx`;
  - `components/subsidy-calculator.tsx`: the scheme picker, with tests in `subsidy-calculator.test.tsx`.
- `src/app/(app)/subsidy-masters/page.tsx`: the route. `src/components/layout/navigation.ts`: Subsidy masters under Admin.
- `src/mocks/`:
  - `data/subsidy-masters.ts`, `data/subsidy-schemes.ts`: new;
  - `data/reference.ts`, `data/territories.ts`: Uttar Pradesh;
  - `handlers/subsidy-masters.ts`, `handlers/subsidy-schemes.ts`, `handlers/subsidy-readiness.ts`: new;
  - `handlers/subsidy.ts`, `handlers/subsidy-applications.ts`: the scheme on the calculator, `for-lead`, the stage list and create;
  - `db.ts`, `handlers/index.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SUBS-012…014.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/subsidy/`: the records.

## Tests

**`src/features/subsidy/lib/subsidy-masters-lib.test.ts`:**

- `[SUBS-012]`: a figure, a choice and a whole number checked as typed; only changed rows sent, an emptied optional figure as null; today or later.
- `[SUBS-013]`: a matrix copied as a grid and read back; Excel's grouped numbers; each bad cell named; a repeated component refused.
- `[SUBS-014]`: every kind of missing item in words, with its table.

**`src/features/subsidy/api/subsidy-masters.test.ts`:**

- `[SUBS-012]`: a revision closes the old row and starts the new one; a backdated revision and a second one on the same day are refused; each scheme's masters stay apart.
- `[SUBS-013]`: a new scheme's first matrix from blank, and its readiness follows.
- `[SUBS-014]`:
  - GGRC listed, linked to Gujarat, ready;
  - a new scheme: upper-case code, the template's stages, no figures, not ready;
  - a taken code, a covered state and an unknown template refused;
  - an unlinked scheme blocks a new one, is linked once, and its state can't change;
  - a renamed stage shows in the stage list, and a switched-off scheme leaves its leads with `no_scheme_for_state`.

**`src/features/subsidy/components/subsidy-masters.test.tsx`:**

- the GGRC overview, ready on every system, with its stages;
- renaming a stage, refusing an empty name;
- the new-scheme form's checks;
- setting up a scheme, then opening a missing item's table;
- the link banner, linking, then New scheme enabled;
- switching off after the confirm;
- nothing to change for a role without `masters` edit;
- a new scheme's first crop spacing added from a date.

**`src/features/subsidy/components/subsidy-calculator.test.tsx`:** no scheme picker with one scheme; under a second scheme only its systems are open.

**By hand, in Chromium on the mock backend, as an Admin:**

1. The GGRC overview, setting up UPMIS (drip and sprinkler), its readiness, and opening the unit-cost tab from it.
2. The overview and the switch-off confirm on a 360 px phone in dark mode.
3. The calculator as an employee with one scheme: no picker.

axe found nothing on any of these.
