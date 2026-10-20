---
date: 2026-10-15
type: feature
title: "The calculator asks for each scheme's own inputs (CG, RJ, UP, AP)"
dataIds:
  - SUBS-002
  - SUBS-003
author: Nakul Srivastava
breaking: false
---

## Before

Each system in `GET /subsidy/config` lists the extra request fields it needs, in `inputs`. The handover says to build the form from them, never from the state (`state-subsidy-formulas.md`, `andhra-pradesh-subsidy.md`). The calculator read none of them, so:

- CG, RJ and UP couldn't calculate. Sprinklers had no set size; CG and RJ drip had no spacing label; RJ had no filters or existing equipment.
- **An AP drip result failed outright:** the backend sends `regular_matrix_id: null` for it, and the response schema took only a string, so the whole calculation became a contract error.
- **New result rows were dropped:** CG's `fittings` and `flat_inspection`, AP's `gst_paid_by_state`, and RJ's unit-cost `add_ons` and `deductions` disappeared silently.
- **The scheme picker** sent no scheme for whichever active scheme came first in code order. "AP" sorts before "GGRC", so choosing AP calculated under Gujarat.

## Now

- **"The scheme's inputs"** shows, under the head unit, what the system's config lists:
  - a sprinkler set size, 63, 75, 90 or 110 mm (`pipe_size_mm`);
  - a spacing from the scheme's own list (`spacing_label`, from `spacing_labels`);
  - RJ's hydrocyclone and gravel filter (none or a size), and "Farmer already has a head unit" and "… the PVC main line";
  - AP drip's "Guided cost (from the AP MIP portal)" and "Fittings and accessories (from the portal)", with "Copy these, and the lines above, from the portal's bill of quantities."
- A scheme that asks for none, Gujarat today, shows no card and sends exactly what it sent before. An input code the screen doesn't know yet is named in a note rather than ignored.
- **Before sending:** the figures wait for a required input ("Fill in the scheme's inputs to see the subsidy"). A spacing not in the scheme's list, or a money amount that isn't a number, is marked on its field. A backend refusal of any of these lands on its field too.
- **The results:**
  - an AP drip result reads with null matrix ids, and its figure is labelled "Guided cost (the portal's total)";
  - the summary adds "Fittings add-on", "Inspection charge (outside the cap)" and "GST paid by the state" wherever a column isn't zero;
  - RJ's unit cost says what the filters added and what the existing equipment took off.
- **New warnings have titles:** no rate for the set size, a subsidy above the cost, deductions above the unit cost, the pipe size ignored, the guided cost above the cost, the fittings amount above the lines, and an area between table steps.
- **The scheme picker** treats the backend's default, GGRC, as "none", and sends any other scheme by code, wherever it sorts.
- **The mock** lists each state's `inputs` by scheme code (CG, RJ, UP, AP), with invented spacing labels. It refuses a listed input that's missing, and AP's fields on another scheme. It calculates AP drip without a unit cost table, adding the state's half of the GST. Its AP figures are illustrative, not AP's formula.
- Checked on a desktop in light mode and a phone in dark mode: an AP scheme set up in Subsidy masters, then an AP drip quotation before and after the portal's figures. axe found nothing.

## Discussion

- **Please confirm with the backend:** the AP handover asks whether the frontend is fine with `regular_matrix_id` and `seven_year_matrix_id` becoming nullable (breaking under ADR-028). This PR reads them as nullable and doesn't otherwise use them, so yes.
- **One crop and free-text crop names outside Gujarat:** the config's `crop_count_max` already limits the blocks to one. The crop is still chosen from `GET /subsidy/crops`, which serves each scheme's own list.
- **The quotation PDF and the farmer's link** still print without the state's GST for AP; that is the backend's GAP-482.
- **In the mock,** a scheme set up in Subsidy masters has no categories until its masters are entered, so the category preview answers 404 there. That is the mock's existing behaviour for an unfinished scheme.
- **Not yet checked on staging.**

## Files changed

- `src/features/subsidy/api/subsidy.schemas.ts`:
  - config `inputs`, `spacing_labels`, `pipeline` and `cap_mode`;
  - the new request fields;
  - the extra blocks, the jantri add-ons and deductions, and nullable matrix ids;
  - `guidedCost` and `DEFAULT_SUBSIDY_SCHEME`.
- `src/features/subsidy/lib/calculator-draft.ts`: the scheme inputs in the draft, checked, and sent only when listed.
- `src/features/subsidy/components/calculator-inputs.tsx`: `SchemeInputsCard`.
- `src/features/subsidy/components/subsidy-calculator.tsx`: the card, its fields placed for refusals, the waiting message, and the scheme picker's default.
- `src/features/subsidy/components/calculator-results.tsx`, `src/features/subsidy/lib/subsidy-labels.ts`: the guided cost label, the add-ons and deductions, the extra summary rows, and the warning titles.
- `src/mocks/handlers/subsidy.ts`: inputs by scheme, their refusals, and AP drip.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/subsidy/ap-*`: records and screens.

## Tests

- `src/features/subsidy/components/subsidy-scheme-inputs.test.tsx`:
  - a scheme asking for none sends none;
  - AP drip waits for its guided cost and fittings amount, then sends them, and a typo is marked;
  - RJ sends its spacing, filters and existing equipment, and a spacing not in the list is a mistake;
  - a sprinkler asks for its set size;
  - an AP result with null matrix ids and the state's GST reads;
  - the screen, end to end: an AP scheme picked (it sorts before GGRC), the portal's figures entered, the guided cost and "GST paid by the state" shown.
- `src/features/subsidy/lib/calculator-draft.test.ts`: fixtures updated for the new config fields.
- Walked through in the mock: desktop light and phone dark.
