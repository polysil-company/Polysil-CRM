# Andhra Pradesh subsidy (scheme AP)

Full contract: `docs/api/subsidy.md`. Additive, except one type change: `masters.regular_matrix_id` and `masters.seven_year_matrix_id` on the calculate response may now be `null`. **Please confirm you are fine with this change** (it is breaking under ADR-028); regenerate the API types.

For AP drip, `jantri.regular` is the guided cost, a total, not a per-hectare unit cost: label it "Guided cost".

## What changed

A new subsidy scheme, `AP` (Andhra Pradesh Micro Irrigation Project), with two systems:

- **Sprinkler:** works like UP sprinkler. The user picks the set size; the area and category do the rest.
- **Drip:** the AP government portal designs the system and prints the figures. The user copies the portal's lines, its fittings amount and its guided cost into the CRM. The CRM works out the subsidy and the farmer's share from them.

In both, the state pays half the GST. That half is a new figure, `gst_paid_by_state`, and the farmer's share leaves it out.

## Screens

1. **Calculator and subsidised quotation form, scheme AP:** read `GET /subsidy/config?scheme=AP`. Each system's `inputs` says what to ask, as for CG, RJ and UP.
   - Sprinkler: `inputs: ["pipe_size_mm"]`. Same form as UP sprinkler.
   - Drip: `inputs: ["guided_cost", "fittings_amount"]`. Two money inputs, labelled "Guided cost (from the AP MIP portal)" and "Fittings and accessories (from the portal)". The lines are entered as for UP drip: head lines and the crop's lines, each with description, rate and quantity as the portal prints them. Show a note: "Copy these from the portal's bill of quantities."

```
POST /subsidy/calculate
{ "scheme": "AP", "system_type": "drip",
  "crops": [{ "area": "1.02", "lateral_spacing": "5", "lines": [
      { "description": "Plain lateral 16 mm", "uom": "m", "rate": "8.43", "qty": "2310" }] }],
  "head_lines": [{ "description": "Screen filter 40 m3", "uom": "No.", "rate": "2337.76", "qty": "1" }],
  "guided_cost": "134367", "fittings_amount": "6502.55" }
```

2. **Result:** where `blocks.gst_paid_by_state` is not "0.00", show one more row under the GST: "GST paid by the state". Subsidy + farmer's share + this row = the total.
3. **Order from an AP subsidised quotation:** no screen change. The order's `subsidy_amount` is what the government pays, so for AP it is the subsidy plus the state's GST, and `farmer_payable` is the farmer's share.

## Refusals and messages

| Code | When | Say |
|---|---|---|
| `422` field `guided_cost` | AP drip without it, or another scheme with it | "Enter the guided cost from the portal." / drop the field |
| `422` field `fittings_amount` | the same | "Enter the fittings amount from the portal (0 if none)." |
| `422 zero_cost` | AP drip with no lines | "Add the portal's lines." |

## Warnings (show as they come, in the existing warnings list)

- `guided_cost_above_cost`: the guided cost is more than the cost; the subsidy is on the cost.
- `fittings_above_material`: the fittings amount is more than the lines. Likely a typing slip.
- `no_unit_cost_for_size`: AP sprinkler above 2 Ha has no unit cost, so no subsidy (the client is asked).

## Not yet

The farmer's link and the quotation PDF still print total, subsidy and share only, so for AP they look short by the state's GST. Backend change pending (GAP-482).
