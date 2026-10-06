# Company settings, amending an approved order, reopening a complaint

> Full spec: FS-036. All additive.

## Settings (admin)

```jsonc
// GET /api/v1/settings                     staff only
{ "data": [ { "key": "order_amend_reapproval", "value": "always",
              "allowed": ["always", "value_rises"], "description": "...", "updated_at": "..." } ] }

// PATCH /api/v1/settings                   masters.edit, Idempotency-Key
{ "values": { "complaint_reopen_days": 15 } }        // 200 the full list; 422 on a bad value or key
```

Keys today: `order_amend_reapproval` (always | value_rises), `complaint_reopen_days` (1 to 365),
`complaint_reopen_roles` (role codes), `complaint_reopen_clock` (restart | continue),
`complaint_reopen_max` (1 to 10). More keys
arrive with other features; render the list generically from `allowed` and the value's type.

## Amend an approved order

```jsonc
// POST /api/v1/orders/{id}/amend         Idempotency-Key
{ "reason": "Farmer wants 20 more laterals" }
// 200 Order: status "draft", amend_count 1, amended_from_total "105000.00"
// 409 order_has_shipped | order_has_payments | status_changed    422 remark_required | order_type_fixed
```

Only before anything ships and before any payment is allocated. Then edit and submit as usual.
With `value_rises`, a resubmit whose total is not above `amended_from_total` goes straight to
Accounts. The PDF disappears until the order is approved again. Payment instalments are cleared for
Accounts to set again. An amended order cancelled while a draft still needs the delete permission.

## Reopen a complaint

```jsonc
// POST /api/v1/complaints/{id}/reopen    Idempotency-Key
{ "reason": "The same emitters failed again" }
// 200 Complaint: status "submitted", reopen_count 1
// 403 role not allowed    409 status_changed    422 reopen_window_closed | remark_required
```

From `closed` (the raiser or an allowed role) or `qc_rejected` (allowed roles only), within the
window and under the cap. It starts a new round; the timeline shows `complaint.submitted` with
`reopened: true`. It then goes through the check, QC and a remedy again.

## Screens

- Admin: a Settings page.
- Order detail when approved: "Amend" beside "Cancel"; after amend, a banner with the approved total.
- Complaint detail when closed or rejected: "Reopen" while inside the window; "Reopened N times".
