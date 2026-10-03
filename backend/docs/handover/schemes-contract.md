# Schemes

> Admin defines promotional schemes; orders show the benefit; dealers see their schemes and credits. Full spec: FS-031. Every number is a stand-in the admin sets.

## The four types

| `scheme_type` | `benefit.kind` | What happens |
|---|---|---|
| `order_discount` | `pct`, `flat` | taken off what the dealer owes, at submit |
| `order_points` | `points` | points to the dealer when the order is delivered |
| `next_order` | `pct`, `flat` | a credit earned on delivery, used on a later order |
| `period` | `pct`, `flat`, `points` | after each month or quarter: a credit or points if the dealer's delivered total met the target |

A benefit **never changes the invoice**. The order gains `benefits` and `payable`
(total minus applied benefits). Show `payable` as "To pay".

## Admin screens

```jsonc
// POST /api/v1/schemes            (Idempotency-Key)
{ "code": "GJ-DRIP-5", "name": "Gujarat drip 5% above 2 lakh", "description": null,
  "scheme_type": "order_discount",
  "condition": { "metric": "order_value", "min": "200000", "max": null },  // product_qty also
  "benefit": { "kind": "pct", "value": "5", "cap": "50000", "entitlement_days": null },
  "period": null,                     // "month" | "quarter", period schemes only
  "valid_from": "2026-10-05", "valid_to": "2026-12-31",
  "priority": 100, "stackable": false,
  "targets": [ { "type": "territory", "id": "<uuid>" },
               { "type": "partner_type", "id": "dealer" },
               { "type": "product_category", "id": "<uuid>" } ] }
// 201 { "data": Scheme }   422 fields: "benefit.kind", "valid_to", "targets[0].id" ...   409 code_taken

// GET   /api/v1/schemes?status=current|active|inactive&scheme_type=&q=&cursor=
// GET   /api/v1/schemes/{id}
// PATCH /api/v1/schemes/{id}      any create field, plus is_active
//        once "used": true, only valid_to (earlier, not before today) and is_active: else 409 scheme_in_use
```

`Scheme` carries `is_current` and `used`. When `used` is true, make every field but
the end date and the active switch read-only, and say why.

Targets: same type means OR, different types mean AND. `[]` means everyone.

## The order screen

```jsonc
// GET /api/v1/orders/{id}/schemes     (draft only; 409 order_not_draft after submit)
{ "data": {
  "discounts":    [ { "scheme": {"id","code","name"}, "basis": "240000.00", "amount": "12000.00" } ],
  "entitlements": [ { "entitlement_id": "uuid", "scheme": {...}, "amount": "3000.00" } ],
  "on_delivery":  [ { "scheme": {...}, "kind": "points", "points": 200, "basis": "240000.00" } ],
  "total_benefit": "15000.00", "payable": "268200.00" } }
```

Refresh it after the lines change. After submit, read `benefits` on the order:

```jsonc
"benefits": [ { "id": "uuid", "kind": "discount",      // discount | entitlement_used | reward_redemption
                "scheme": {"id","code","name"},        // null for reward_redemption (points)
                "amount": "12000.00", "status": "applied", "applied_at": "..." } ],
"payable": "268200.00"
```

A `reversed` benefit (the order went back to draft or was cancelled): show it struck through.

## Dealer portal

- `GET /api/v1/schemes?status=current`: a dealer sees only schemes aimed at it.
- `GET /api/v1/schemes/{id}/standing`: period schemes only, for a progress bar.

```jsonc
{ "data": { "period_start": "2026-10-01", "period_end": "2026-10-31", "metric": "order_value",
            "achieved": "420000", "min": "500000", "max": null, "qualifies": false } }
```

- `GET /api/v1/scheme-entitlements?status=available`: the dealer's credits, with
  `expires_at`. Credits are used automatically on the next order they fit.

## Errors to handle

| Code | Where |
|---|---|
| `scheme_in_use` (409) | PATCH on a used scheme |
| `code_taken` (409) | create |
| `not_a_period_scheme` (422) | standing |
| `order_not_draft` (409) | preview after submit |
