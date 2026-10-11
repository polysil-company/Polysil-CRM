# Accounts queue, order names on the timeline, one conversation

> Full spec: FS-029. Answers BE-014, BE-020, BE-021 and BE-022. All additive.

## BE-020 · The order on the lead timeline

Every event about an order on `GET /api/v1/leads/{id}/timeline` now carries two payload fields. That includes `order.*`, `dispatch.*`, `approval.decided` and `payment.*`.

```jsonc
{ "kind": "order.submitted",
  "payload": { "order_id": "9b1c...", "order_no": "SO/GJ/2026-27/00012", ... } }
```

- `order_no` is null until the order is submitted.
- Old events have both fields too, since they are added when read.
- `timeline-entries.ts` already reads them, so the links should appear with no change.

## BE-021 · One conversation

```jsonc
// GET /api/v1/conversations/{conversation_id}      staff only
{ "data": { "id": "...", "participant": { "id": "...", "full_name": "...", "role_name": "...",
            "org_unit_name": "...", "is_active": true },
            "last_message": null, "unread_count": 0, "updated_at": "..." } }
// 404 not yours, or no such conversation
// 422 not a uuid
// 403 a dealer
```

It works before anyone has written, so the thread header can name the colleague after a reload or from a link.

## BE-022 · The Accounts queue

`waiting_on` is a new filter on `GET /orders`, `GET /orders/stats` and `GET /orders/export`. It takes a role code and matches orders whose next approval step is that role's. It is the same rule as the row's `approval_waiting_on`.

```jsonc
// the queue
GET /api/v1/orders?waiting_on=account_manager&include_total=true
// the badge: call stats WITHOUT waiting_on and read waiting_on.account_manager
GET /api/v1/orders/stats            → { ..., "waiting_on": { "account_manager": 3, ... } }
```

- An unknown role code gives an empty list. A malformed one is 422.
- With `waiting_on` on stats, every count narrows to the matches.
- It names the step's role. A stalled District Manager step stays `district_manager`, though a State Manager may decide it.

**What Accounts records besides the remark:** payments, already built (handover 30). They are `GET/POST /api/v1/payments` and `payments` on `GET /orders/{id}` (payable, received, balance). A queue row can link to "Record payment".

## BE-014 · Approval limits

There is nothing to build. `GET /api/v1/approvals/thresholds` and `PUT` (Admin) set the order and discount limits per role. The figures in the seed are stand-ins: 1,00,000 for a District Manager and 5,00,000 for a State Manager. The client owes the real ones (question 15.1).
