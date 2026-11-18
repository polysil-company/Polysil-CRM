# Subsidised quotations

Full contract: `docs/api/quotations.md`. Additive; other quotations are unchanged.

## What changed

A quotation on a subsidised lead can now be `sales_type: "subsidised"`. It carries the subsidy calculator's answer for one category, prints it, and becomes a subsidised order with the subsidy filled in.

## Screens

1. **New quotation** on a subsidised lead: lines as today.
2. **Subsidy step** (draft only): show the subsidy calculator form for the lead's scheme. Build it from `GET /subsidy/config?scheme=<lead's scheme>` (`GET /subsidy-schemes/for-lead/{lead_id}` gives the scheme). After a calculation, the user picks a category and saves:

```
PUT /quotations/{id}/subsidy
{ "category_code": "small_farmer",
  "calculation": { ...the same body as POST /subsidy/calculate, without "scheme"... } }
```

   Returns the quotation with `subsidy`:

| Field | Meaning |
|---|---|
| `scheme`, `system_type`, `category` | what it was calculated on |
| `total_cost` | the cost as calculated, with any CG inspection charge |
| `subsidy` | what the scheme pays |
| `farmer_share` | what the farmer pays |
| `as_of` | the masters' date |

   Save again to recalculate. Show the warning `calculation_total_differs` in plain words: "The calculation's total differs from the quotation's lines. Recalculate if the lines changed."

3. **Send / request approval**: a subsidised quotation without a subsidy gets `422 subsidy_missing` ("Calculate the subsidy first"). `422 subsidy_scheme_changed`: the lead moved state; recalculate.
4. **Detail**: show the subsidy block. The PDF and the farmer's link show it too.
5. **Create order** from an accepted subsidised quotation: `POST /orders { "order_type": "subsidised", "quotation_ids": ["<one id>"] }`. Do not send `subsidy`; it comes from the quotation. The order's subsidy block shows material, subsidy and farmer payable.

## Refusals

| Code | When |
|---|---|
| `422 not_subsidised` | the quotation is not subsidised |
| `409 quotation_not_draft` | it was sent |
| `422` on `category_code` | the category does not apply on every crop |
| `422` on `calculation.scheme` / `calculation.system_type` | not the lead's |
| `422 subsidy_block_exists` | changing the sales type of a quotation with a subsidy |
| `422 subsidised_quotation_count`, `subsidy_from_quotation`, `quotation_subsidy_missing`, `type_mismatch` | order creation |
