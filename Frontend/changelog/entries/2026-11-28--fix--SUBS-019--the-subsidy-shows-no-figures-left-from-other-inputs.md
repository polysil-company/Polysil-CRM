---
date: 2026-11-28
type: fix
title: The subsidy shows no figures left from other inputs
dataIds:
  - SUBS-019
  - SUBS-002
  - SUBS-004
  - QUOT-014
author: Nakul Srivastava
breaking: false
---

## Before

The client reported that the subsidy "calculation is not working correctly" on a lead and on a quotation (28 Nov). Their screenshot of _Start a subsidy application_ (GGRC, Drip, 1.61 Ha mango) showed:

- a field-unit item "pipe" and a head-unit item "inlet" typed, with no unit, rate or quantity, each marked "Give its unit";
- "Correct the marked fields to see the subsidy." at the top;
- and still a full set of figures: ₹700 subsidy and ₹300 for the farmer per category, and a quotation summary of ₹0 for every block but ₹1,000 of farmer education.

Those figures came from the last inputs that could be calculated, before the items were added. The panel only dimmed them to 60%, so they read as the subsidy for what was on screen.

The backend's arithmetic was right: 70% of ₹1,000 is ₹700. The calculator, _Start a subsidy application_ and a quotation's subsidy share this panel, so all three did it.

## Now

- Once typing pauses on inputs that can't be calculated, the subsidy and the quotation summary go. That covers a mistake, a missing field, or a refusal from the backend. The panel lists the farmer categories without figures, and the status says what to do, such as "Correct the marked fields to see the subsidy."
- Finishing the inputs brings the figures back. While a valid change recalculates, the last figures still dim for that moment, as before.
- A field-unit or head-unit row's boxes are named "Item of field unit item 1" for screen readers. They were "Itemof…".

## Discussion

- **The rest of the client's report is BE-045.** The designer types each item's rate, and installation and the sump per hectare, because a subsidy line still carries its own rate (the backend's GAP-080). The client wants the rates from the subsidised price list, with installation, sump, secondary transportation and PVC/HDPE fittings priced per hectare from the area. BE-045 asks for it, with three decisions for the client; plan item 52 is the frontend's half, waiting on it.
- Waiting for the pause keeps the figures from flickering while a number is half typed ("1." on the way to "1.5").

## Files changed

- `src/features/subsidy/hooks/use-subsidy-calculation.ts`: no result once the paused inputs can't be calculated.
- `src/features/subsidy/components/calculator-inputs.tsx`: the space in each row box's name.
- `src/features/subsidy/components/subsidy-calculator.test.tsx`: SUBS-019.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md` (items 52 and 53).
- `../docs/Backend-Tasks.md`: BE-045.

## Tests

- `subsidy-calculator.test.tsx`, `[SUBS-019] No figures left from other inputs`:
  - figures for 1.61 Ha;
  - a field-unit item named "pipe" alone clears the subsidy and the summary, and says to correct the marked fields;
  - adding its unit, rate and quantity brings the figures back.
- The other subsidy suites (calculator, applications, quotation subsidy) pass unchanged.
