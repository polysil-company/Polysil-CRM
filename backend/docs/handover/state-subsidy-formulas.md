# Subsidy formulas for Chhattisgarh, Rajasthan and Uttar Pradesh

Full contract: `docs/api/subsidy.md`. Everything is additive; Gujarat (GGRC) is unchanged.

## What changed

The CG, RJ and UP schemes now calculate the way the client's own sheets do. Each asks for a few inputs Gujarat does not.

## Ask the config which inputs to show

`GET /subsidy/config?scheme=CG` lists only the systems that scheme has (CG has no mini sprinkler). Each system now carries:

| Field | Meaning |
|---|---|
| `inputs` | the extra request fields to show for this system |
| `spacing_labels` | the spacing choices, for a system whose inputs include `spacing_label` |
| `pipeline`, `cap_mode` | for display or debugging only |

Build the calculator form from `inputs`. Do not hard-code states.

## The new request fields on `POST /subsidy/calculate`

| Field | Shown when `inputs` has it | Control |
|---|---|---|
| `pipe_size_mm` | sprinkler in CG, RJ, UP | a choice: 63, 75, 90, 110 mm |
| `spacing_label` | CG drip, RJ drip, RJ mini sprinkler | a dropdown of `spacing_labels` |
| `hydrocyclone_m3` | RJ drip and mini | a choice: none, 20, 25, 30 |
| `gravel_filter_m3` | RJ drip and mini | a choice: none, 10, 20, 25, 30 |
| `head_unit_existing` | RJ drip and mini | a yes/no toggle: "Farmer already has a head unit" |
| `pvc_existing` | RJ drip and mini | a yes/no toggle: "Farmer already has the PVC main line" |

Other rules:
- Outside Gujarat a quote has **one crop**, no group area, and the crop name is free text.
- For a sprinkler in these states, `nozzle` may be left out: the scheme's one nozzle is used.
- The lateral spacing field is still required for drip; send the designed spacing.

## The new response fields

| Field | Meaning |
|---|---|
| `blocks.fittings` | CG drip's 4 % fittings add-on |
| `blocks.flat_inspection` | CG's inspection charge (1003 drip, 295 sprinkler). It is outside the cap and included in the farmer's share |
| `jantri.add_ons`, `jantri.deductions` | RJ: filters added to the unit cost, existing equipment taken off. `regular_for_cap` is the final unit cost |

New warnings, shown in plain words:

| Warning starts with | Say |
|---|---|
| `no_unit_cost_for_size` | No subsidy rate for this set size at this area |
| `subsidy_above_cost` | The scheme's sheet gives a subsidy above the cost |
| `area_above_table` | The area is above the scheme's table; no subsidy |
| `unit_cost_below_zero` | The deductions are more than the unit cost |
| `pipe_size_ignored` | This scheme sets the pipe size by area |

## Refusals

`422` naming the field: `pipe_size_mm` (missing or not a size), `spacing_label` (missing or not one of the list), `hydrocyclone_m3` / `gravel_filter_m3` (a size the scheme has no rate for), `crops` (more than one crop, or a quote with no cost).
