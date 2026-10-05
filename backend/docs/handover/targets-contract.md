# Targets and achievement

> **Status: built on the backend.** These shapes are what the API returns. They only gain fields from here.

Managers set monthly targets for the people below them. Everyone sees their target against what they have achieved so far this month, live.

All paths are under `/api/v1`. Months are `YYYY-MM`.

## Who can do what

| Role | Sees | Sets targets for |
|---|---|---|
| Field officer | own | nobody |
| District, state, regional manager | their team | people below them in office and rank (not themselves, not a peer) |
| Admin, MD | everyone | anyone |
| Board | everyone | nobody |

## Set targets: `PUT /targets` (Idempotency-Key required)

```json
{ "user_id": "uuid", "month": "2026-10",
  "targets": { "order_value": "500000.00", "orders": 10, "leads_won": 8, "visits": 60 } }
```

- Send any of the four; the others keep their value. 0 clears a target.
- Answers `200` with the same shape as `GET /targets`.
- `403 not_your_team`; `422 month_closed` (a past month, unless admin or MD); `422 user_inactive`; `422` for a negative value or a fractional count.

## A person's targets: `GET /targets?user_id=&month=`

```json
{ "data": { "user": { "id": "uuid", "full_name": "Ravi Patel" }, "month": "2026-10",
  "targets": { "order_value": "500000.00", "orders": 12, "leads_won": null, "visits": null },
  "history": [ { "metric": "orders", "value": 12, "set_by": { "id": "uuid", "full_name": "…" }, "set_at": "…" } ] } }
```

## Achievement: `GET /targets/achievement?month=&user_id=`

```json
{ "data": { "month": "2026-10", "as_of": "…",
  "rows": [ { "user": { "id": "uuid", "full_name": "Ravi Patel" },
              "metrics": { "order_value": { "target": "500000.00", "achieved": "318000.00", "pct": "63.6" },
                           "orders": { "target": 10, "achieved": 6, "pct": "60.0" },
                           "leads_won": { "target": null, "achieved": 3, "pct": null },
                           "visits": { "target": 60, "achieved": 41, "pct": "68.3" } } } ],
  "totals": { "orders": { "target": 10, "achieved": 6, "pct": "60.0" } } } }
```

- Without `user_id`: you and everyone below you, **with or without a target**. A field officer gets one row.
- `achieved` is `null` for a measure the user may not see; show "not available". `pct` is `null` without a target.

## Screens

| Screen | Notes |
|---|---|
| My targets | four progress bars for the month; month picker |
| Team targets | a row per person; Set targets opens four number fields; history from `GET /targets` |

## Defaults the client has not confirmed

- Monthly targets per person, on these four measures.
- No dealer or territory targets yet.
- Managers cannot change a past month's targets; admin can.
