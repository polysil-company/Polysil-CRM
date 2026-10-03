# Subsidy ageing, reports and masters administration

> The client's ageing figures, the stage dashboard, the supply report, and revising the subsidy masters from the app. Full spec: FS-009a.

## Ageing

```jsonc
// GET /api/v1/subsidy-reports/ageing?status=&stage=&q=&cursor=      (+ /export)
{ "data": [ {
  "application": { "id", "application_no", "reg_no", "farmer_name", "status", "stage", "district" },
  "today_to_supply":                { "days": 41, "running": true,  "since": "2026-08-23", "until": null },
  "inward_to_submission":           { "days": 12, "running": false, "since": "...", "until": "..." },
  "wo_to_tpa_received":             { "days": null, "running": false, "since": null, "until": null },
  "tpa_cleared_to_inspection_sent": { ... },
  "inspection_sent_to_tr":          { ... },
  "fp_submitted_to_full_fp":        { ... } } ],
  "meta": { "next_cursor": null } }
```

`days` null: the start is not recorded. `running`: no end yet, counted to today.

## Reports

```jsonc
// GET /api/v1/subsidy-reports/stages?status=open       (+ /export)
{ "data": [ { "seq": 9, "code": "wo_issued", "name": "...", "count": 14, "total_cost": "...",
              "subsidy": "...", "farmer_share": "...", "oldest_days_in_stage": 63 } ] }

// GET /api/v1/subsidy-reports/supply                    (+ /export)
{ "data": [ { "district": "Rajkot", "supplied": 31, "not_supplied": 12,
              "supplied_cost": "...", "not_supplied_cost": "..." } ] }
```

## Subsidy masters (admin)

```jsonc
// GET  /api/v1/subsidy-masters/{kind}?scheme=GGRC&on=2026-10-03
//      kind: categories | parameters | component-rates | crop-spacings
// POST /api/v1/subsidy-masters/{kind}/revisions
{ "scheme": "GGRC", "effective_from": "2027-04-01",
  "rows": [ { "key": "per_ha_cap", "value": "70000", "unit": "rupees" } ] }   // the table's own row shape
// 201 { "data": { "closed": 1, "inserted": 1, "effective_from": "2027-04-01" } }
// 409 revision_on_start_date | later_revision_exists   422 revision_in_past

// GET  /api/v1/subsidy-masters/{unit-cost-matrices|quantity-matrices}/matrices?on=   in force, with cells
// POST /api/v1/subsidy-masters/{unit-cost-matrices|quantity-matrices}/matrices
{ "scheme": "GGRC", "system_type": "drip", "variant": "regular", "dimensionality": 2,
  "effective_from": "2027-04-01", "source": "GGRC circular 12/2027",
  "unit_cost_cells": [ { "lateral_spacing": "1.2", "area_breakpoint": "0.4", "unit_cost": "112000" } ] }
```

Row shapes (see the generated API doc): `CategoryRow`, `ParameterRow`,
`ComponentRateRow`, `CropSpacingRow`. A revision starts today or later; quotations and
applications dated before it keep the old figures.

Not built: the printed GGRC quotations and consent letters (GAP-331, GAP-333).
