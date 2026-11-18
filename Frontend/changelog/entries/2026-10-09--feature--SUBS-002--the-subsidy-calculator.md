---
date: 2026-10-09
type: feature
title: The subsidy calculator
dataIds:
  - SUBS-002
  - SUBS-003
author: Nakul Srivastava
breaking: false
---

## Before

Subsidy was a "Soon" item in the sidebar. The backend has served the GGRC calculation since its subsidy module (`POST /subsidy/calculate`, `GET /subsidy/config`, `/crops`, `/categories`; handover `subsidy-calculation.md`). The web app couldn't show a designer or a farmer what the scheme pays.

The mock also gave dealers and distributors `subsidy`, though the backend answers portal users 403 on every subsidy endpoint.

## Now

- **Sales → Subsidy** opens the calculator (`/subsidy/calculator`), for staff with `subsidy`. Dealers and distributors neither see it nor reach it.
- **Three tabs: Drip, Mini Sprinkler and Sprinkler** (`?system=`). Each is shaped by `GET /subsidy/config`, not hard-coded:
  - how many crop blocks it takes (two on Drip);
  - whether it has a head unit and a group's area;
  - which areas Sprinkler may use.

  Each tab keeps its own inputs while the designer moves between them.

- **The inputs:**
  - per crop block: the crop and inter-crop, each showing its standard spacing; the area; the lateral spacing; the crop spacing as it prints; the field-unit items (item, unit, rate, quantity);
  - the head unit, once for the quotation;
  - installation and sump, per hectare;
  - a group's total area, for farmers sharing one water source;
  - on Sprinkler, the nozzle. Its area comes from the scheme's steps, and it takes no items.
- **The figures follow the inputs,** recalculated after a pause in typing:
  - the warnings, each with a title, the block it is about, and the seven-year ones kept apart;
  - per block, the designed, standard and used spacing, and why when the standard wins;
  - per block, the unit cost the scheme allows (`regular_for_cap`) and the seven-year one;
  - all eight farmer categories, with the subsidy, its share and what the farmer pays. GSDMA shows where it applies, and a category that doesn't apply stays, greyed, with its reason;
  - the 22-row quotation summary, a column per block and the total;
  - on Sprinkler, the derived items, the pipe size and the DBT farmer payable.

  Older figures stay, dimmed, while new ones load. Nothing is saved.

- **Before anything is calculated,** the eight categories are listed with their percentages.
- **Mistakes and refusals:**
  - A missing area or spacing just waits.
  - Too many decimals, a half-typed item, or a group's area of 0 is named on its field once typing pauses.
  - A refusal from the backend (`crops[0].area`, `group_total_area`…) lands on the same field. One no field shows is listed above the figures.
  - Anything else shows an error with a retry.
- Checked at 360 px, light and dark, with no sideways scroll.

## Discussion

**Decisions:**

- **The screen prints, never computes.** Money, areas and unit costs stay the backend's decimal strings until they are formatted. Columns are never added on screen, so a summary that misses by a paisa matches the scheme's sheet, as the handover asks. The only arithmetic is turning a rate from the masters into a percentage for a label ("D · Insurance (0.28%)").
- **Every request path is the backend's.** The draft becomes the request in one pure function. Its own checks use the backend's field paths (`crops[0].lines[1].rate`), so a local mistake and a 422 land on the same input. Blank item rows aren't sent, and paths count only the rows that are.
- **Three screens, not one form with toggles,** as the handover says. A system's keys are left out of the request rather than sent empty: Sprinkler sends no lines, head unit, sump or group; the others send no nozzle.
- **`/subsidy/calculator`, not `/subsidy`.** Subsidy applications come next and take `/subsidy`; the calculator then becomes one tab beside them.
- **Channel partners lose `subsidy` in the mock,** matching the backend. The nav item is staff-only as well.

**The mock:**

- The mock follows the scheme's shape: the 8 categories per system, Sprinkler's area steps and pipe bands, the rates in the masters, and the refusals by field path.
- Its arithmetic and crop spacings are a stand-in, not the client's figures. Only the backend's engine reproduces the workbooks.

## Files changed

- `src/features/subsidy/`: new.
  - `api/`: schemas, API, queries, and `subsidy.test.ts`.
  - `lib/calculator-draft.ts`: the draft, its checks and the request; `subsidy-labels.ts`: systems, the summary's rows, warning titles. With `calculator-draft.test.ts`.
  - `hooks/use-subsidy-calculation.ts`: the debounced calculation.
  - `components/`: `subsidy-calculator.tsx` (the page and its tabs), `calculator-inputs.tsx`, `calculator-results.tsx`, `crop-picker.tsx`, and `subsidy-calculator.test.tsx`.
- `src/app/(app)/subsidy/calculator/`: the route.
- `src/components/layout/navigation.ts`: Subsidy opens the calculator, staff only.
- `src/mocks/`: `handlers/subsidy.ts`, `data/subsidy.ts`, the handler list, and `subsidy` taken from channel partners in `data/permissions.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SUBS-002 and SUBS-003.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/subsidy/`: the records.

## Tests

**`src/features/subsidy/api/subsidy.test.ts`:**

- `[SUBS-003]`: the config, crops and categories; a dealer gets 403.
- `[SUBS-002]`:
  - the blocks, the unit cost and eight categories, as decimal strings;
  - the inter-crop sets the standard spacing;
  - a refusal names its field;
  - Sprinkler derives its lines and refuses an area off the table.

**`src/features/subsidy/lib/calculator-draft.test.ts`:**

- nothing is sent until area and spacing are in;
- the request is built as typed, without blank rows;
- mistakes are keyed by the backend's paths;
- Sprinkler sends only what it takes;
- row paths skip blank rows;
- warnings are split, with the seven-year prefix;
- rates print as percentages.

**`src/features/subsidy/components/subsidy-calculator.test.tsx`:**

- the categories first, then the figures;
- the spacing the subsidy uses when the inter-crop's standard is wider;
- a local mistake, and the backend's refusal, on their fields;
- two crop blocks on Drip;
- Sprinkler with a tabulated area and a nozzle;
- a dealer is refused.

**By hand, in Chromium on the mock backend, as a field employee:**

1. The empty calculator on a phone.
2. Drip with items and installation, then a refusal and a mistake.
3. Two crop blocks in dark mode.
4. Sprinkler on a 360 px phone in dark mode.

axe found nothing on any of these.
