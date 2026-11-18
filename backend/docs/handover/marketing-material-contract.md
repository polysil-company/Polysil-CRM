# Marketing material ordering

> The 17-item catalogue, an order with company and dealer shares, District Manager approval, dispatch. Full spec: FS-034. Money is a decimal string.

## Catalogue

```jsonc
// GET /api/v1/marketing-materials?active=true
{ "data": [ { "id", "code": "MM-CAP", "name": "POLYSIL CAP", "unit": "Nos", "price": "120.00",
              "company_share_pct": "50.00", "image_url": null, "is_active": true, "is_provisional": true } ] }
```

`is_provisional`: a stand-in price, show "indicative". Admin (`marketing_material.edit`):
`POST /marketing-materials`, `PATCH /marketing-materials/{id}` (a new price starts
today; a price set today can be corrected the same day until an order uses it, then
`409 price_changed_today` until tomorrow).

## Ordering

```jsonc
// POST /api/v1/marketing-orders     (Idempotency-Key)
{ "partner_id": "uuid" | null,     // a dealer: ignored. Staff: the dealer, or null for office use (company pays all)
  "lines": [ { "material_id": "uuid", "qty": 20 } ], "remark": "For the Anand meet" }
// 201 { "data": MarketingOrder }    422 material_inactive, a line listed twice
```

`MarketingOrder`: `order_no` (`MM/GJ/2026-27/00004`), `status` (`submitted`,
`approved`, `rejected`, `cancelled`, `dispatched`), `partner`, `requested_by`, `office`,
`lines` (price and shares copied at order time), `totals` (`value`, `company_share`,
`dealer_share`), `decision`, `dispatch`, and **`can`**: `{ approve, reject, cancel,
dispatch }` for the caller. Show buttons from `can`.

```jsonc
// GET  /api/v1/marketing-orders?status=&partner_id=&awaiting=me&mine=true&cursor=
// GET  /api/v1/marketing-orders/export?...
// POST /api/v1/marketing-orders/{id}/approve   { "remark": null }
// POST /api/v1/marketing-orders/{id}/reject    { "remark": "..." }        required
// POST /api/v1/marketing-orders/{id}/cancel    { "remark": null }         required once approved
// POST /api/v1/marketing-orders/{id}/dispatch  { "dispatched_on": "2026-10-08", "reference": "DTDC 123" }
// 403 own_order | not_your_approval    409 status_changed    422 remark_required
```

The order's office is the dealer's area for a dealer's own order, and the requester's own
office for a staff order. The approver is the District Manager over that office (or above,
or admin and the marketing team). Nobody approves their own order. A dealer never sees who decided.

## Screens

Catalogue cards with "Add"; order form with both shares; My orders; Approvals
(`awaiting=me`); Marketing team "To dispatch" (`status=approved`); admin catalogue.
