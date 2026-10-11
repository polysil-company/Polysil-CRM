# Warranty tracking

> Full spec: FS-046. All additive.

## On the order page: a Warranty tab

`GET /api/v1/orders/{id}/warranty` (needs sales_orders.view and dispatch.view)

```jsonc
{ "data": {
  "order_id": "uuid", "order_no": "SO/GJ/2026-27/00012",   // null on a draft
  "order_type": "commercial",
  "replacement_for": null,      // or { "complaint_id": "uuid", "complaint_no": "..." } on a replacement order
  "lines": [ {
    "order_line_id": "uuid", "product": { "id": "uuid", "description": "16mm lateral, 4 lph" },
    "qty_ordered": "500.000", "qty_dispatched": "300.000",
    "status": "active",          // active | expired | none | unknown | not_dispatched
    "dispatches": [ { "dispatch_id": "uuid", "dispatch_no": "DS/...", "qty": "300.000",
                      "start": "2026-10-02", "start_basis": "dc_date",   // or dispatched_at
                      "end": "2027-10-01", "months": 12, "status": "active" } ],
    "claims": [ { "complaint_id": "uuid", "complaint_no": "Poly/Comp./...", "status": "qc_approved",
                  "raised_on": "2026-12-01", "defective_qty": "20.000", "warranty_status": "in_warranty" } ]
  } ] } }
```

Chips: `active` "In warranty until <end>", `expired` "Expired <end>", `none` "No warranty", `unknown` "No period on record", `not_dispatched` a dash.

## On the complaint page: each product line

`GET /api/v1/complaints/{id}`: every entry in `lines` now has

```jsonc
"warranty": { "status": "in_warranty",   // in_warranty | expired | none | unknown
              "start": "2026-10-02", "end": "2027-10-01", "months": 12,
              "basis": "dispatch" }      // dispatch | supply_date | null
```

Compared with the day the complaint was first submitted (today for a draft). Show "from the dispatch" or "from the supply date" under the chip. Out of warranty does not block anything.

## Admin: warranty periods

- `GET /api/v1/warranty-terms` (masters.view): every period, the default first (`product_category: null`).
- `POST /api/v1/warranty-terms` (masters.edit, Idempotency-Key): `{ "product_category_id": "uuid" | null, "months": 0-120, "effective_from": "YYYY-MM-DD" }`. Returns the whole list.
  - `effective_from` must be tomorrow (IST) or later: `422 fields.effective_from`.
  - `409 term_exists`: one already starts that day for that category.
  - 0 months means no warranty.
- A row is in force from `effective_from` up to the day before `effective_to`.

Stand-in until the client answers: 12 months for every category.
