# Dealer commission and TOD (subsidy stage 18)

> After full FP is received, the co-ordinator records the dealer's commission; Accounts approves and pays. Full spec: FS-033. Money is a decimal string.

## On the application (a "Stage 18" tab)

```jsonc
// GET /api/v1/subsidy-applications/{id}/commission/preview
{ "data": { "partner": {"id","name"}, "cost_excl_gst": "254300.00", "a_plus_b": "231000.00",
            "installation": "4500.00", "commission_pct": "5", "tod_pct": "2", "rate_id": "uuid" } }
// 409 not_closed (before full FP)   422 no_partner   commission_pct null = no rate: ask the admin

// POST /api/v1/subsidy-applications/{id}/commission     (Idempotency-Key)
{ "gi_fitting": "12000", "pvc_hdpe_fitting": "8400",
  "installation": null,        // null takes it from the calculation
  "tod_base": null,            // null = same as the commission base
  "remark": null }
// 201 { "data": Commission }   409 commission_exists (approved or paid)   422 fittings above the cost

// GET /api/v1/subsidy-applications/{id}/commission     the live one, or 404
```

`Commission`: every figure (`commission_base`, `commission_amount`, `tod_amount`,
`total`), `status` (`calculated`, `approved`, `returned`, `paid`, `cancelled`), who
recorded and decided, `decision_remark`, `paid_on`, `payment_reference`.

Recording again while `calculated` or `returned` replaces the figures.

## Accounts

```jsonc
// GET  /api/v1/dealer-commissions?status=calculated     to approve
// GET  /api/v1/dealer-commissions?status=approved       to pay
// GET  /api/v1/dealer-commissions/export?...            Excel
// POST /api/v1/dealer-commissions/{id}/approve  {}                       403 own_decision for its recorder
// POST /api/v1/dealer-commissions/{id}/return   { "remark": "..." }      remark required
// POST /api/v1/dealer-commissions/{id}/cancel   { "remark": "..." }
// POST /api/v1/dealer-commissions/{id}/pay      { "paid_on": "2026-10-20", "payment_reference": "NEFT UTR ..." }
// 409 status_changed
```

## Admin: rates

```jsonc
// GET  /api/v1/commission-rates?scheme=GGRC
// POST /api/v1/commission-rates  { "scheme": "GGRC", "system_type": null, "partner_type": "dealer",
//                                  "partner_id": null, "commission_pct": "5", "tod_pct": "2",
//                                  "effective_from": "2026-04-01" }
```

Rates are never edited; add a later one. Dealers do not see commissions yet (GAP-330).
