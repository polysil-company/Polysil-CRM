# Reward points

> Dealers and staff earn points; dealers spend them on an order or a gift. Full spec: FS-032. Points are integers; money is a decimal string.

## Earning (nothing to call)

Earned automatically by rules the admin sets: on a delivered order (for the dealer, and
for the staff owner), and on a won lead (for the staff owner). Schemes can award points
too. A voided dispatch takes them back.

## Balances and history

```jsonc
// GET /api/v1/rewards/balance                 a dealer: its own; staff: their own
// GET /api/v1/rewards/balance?partner_id=     staff: a dealer they can see (managers)
// GET /api/v1/rewards/balance?user_id=        staff: a team member (managers)
{ "data": { "holder": {"type": "partner", "id": "uuid", "name": "Shah Irrigation"},
            "balance": 1240, "point_value": "1.00" } }

// GET /api/v1/rewards/ledger?partner_id=|user_id=&cursor=
{ "data": [ { "id", "points": 240, "kind": "earned", "reason": "...", "at": "...", "expires_at": null } ],
  "meta": { "next_cursor": null } }
```

`kind`: `earned`, `redeemed` (held for a request), `released` (given back), `reversed`,
`expired`, `adjusted`. A field officer sees only their own points.

## Spending

```jsonc
// on a draft order, by the dealer's own user
// POST   /api/v1/orders/{id}/reward-redemption   { "points": 500 }
// DELETE /api/v1/orders/{id}/reward-redemption
// 422 insufficient_points | over_redeem_limit (more than 10% of the order total)   409 points_on_order
```

At submit the points come off `payable` as a benefit with `kind: "reward_redemption"`
and `scheme: null`. Points not needed go back. Only whole points are spent: if the
limit is ₹17.40, the dealer spends 17 points for ₹17.00 and the rest goes back.

```jsonc
// gifts
// GET  /api/v1/gifts?active=true
// POST /api/v1/rewards/gift-redemptions             { "gift_id": "uuid" }    points held at once
// GET  /api/v1/rewards/gift-redemptions?status=pending
// POST /api/v1/rewards/gift-redemptions/{id}/fulfil    { "remark": null }      admin; not the requester
// POST /api/v1/rewards/gift-redemptions/{id}/reject    { "remark": "..." }     remark required; points back
// POST /api/v1/rewards/gift-redemptions/{id}/withdraw  {}                      the requester; points back
// 409 redemption_closed once decided
```

## Admin

```jsonc
// POST  /api/v1/reward-rules   { "code", "name", "holder": "partner"|"staff",
//                                "basis": "order_value"|"lead_won", "points": 1, "per_amount": "1000",
//                                "valid_from", "valid_to": null, "expiry_days": 365 }
// GET   /api/v1/reward-rules,  PATCH /api/v1/reward-rules/{id}   (409 rule_in_use once it has awarded points)
// GET   /api/v1/reward-settings   PUT { "point_value": "1.00", "max_redeem_pct": "10" }  (once a day)
// POST  /api/v1/gifts   PATCH /api/v1/gifts/{id}
// POST  /api/v1/rewards/adjustments   { "partner_id" | "user_id", "points": -50, "reason": "..." }
```

## Screens

- Dealer portal, Rewards: balance, history, gift catalogue with "Request".
- Dealer order draft: "Use points" (balance, the 10% limit).
- Admin: rules, settings, gifts, the gift desk (`status=pending`).
- Staff below admin cannot redeem yet (GAP-336); show their balance and history only.
