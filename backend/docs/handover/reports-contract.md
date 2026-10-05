# Reports and the 360° lead view

> **Status: built on the backend.** These shapes are what the API returns. They only gain fields from here.

Seven reports for managers and HQ, plus a 360° view of a lead. Every figure counts only what the user may see, just like the lists. **A figure the user has no right to is `null`, never 0.** Show `null` as "not available to you".

All paths are under `/api/v1`. Reads only; no `Idempotency-Key`.

## Common parameters

| Parameter | Meaning |
|---|---|
| `from`, `to` | Indian dates, inclusive. Default: the last 30 days. At most a year; `422` if backwards |
| `territory_id` | up to 20, comma-separated |
| `owner_id` | one person |
| `format` | `json`, or `xlsx`, which answers `501 export_not_ready` for now: disable the Excel button on 501 |

Every report answers `{ "data": { "rows": [...], "totals": {...}, "truncated": false, "filters": {...} } }`. At most 1,000 rows; `truncated: true` beyond, with totals still over everything. Money is a decimal string; percentages are strings like `"12.8"`.

`403` means the user may not run this report. Try each report on the reports home page and hide the ones that answer 403.

## The reports

| Path | Rows | Notes |
|---|---|---|
| `/reports/lead-conversion?group_by=source\|owner\|territory` | `key {id, label}`, `leads`, `contacted`, `qualified`, `quoted`, `won`, `lost`, `open`, `conversion_pct` | leads created in the window. `group_by=owner` has an "Unassigned" row (`key.id` null) |
| `/reports/salesperson-performance` | `user`, `leads_created`, `leads_won`, `quotations_sent`, `orders`, `order_value`, `visits`, `tasks_done`, `tasks_overdue` | staff only; the last four may be null |
| `/reports/lost-leads?group_by=reason\|owner` | `key`, `count`, `share_pct`, `avg_days_to_loss`, `by_stage` (`{"quoted": 4, …}`) | `by_stage` is where they dropped off |
| `/reports/follow-ups` | `user`, `due_today`, `overdue_1_2`, `overdue_3_7`, `overdue_8_30`, `overdue_31_plus`, `oldest_due_at` | staff only; as of now; no dates |
| `/reports/dealer-performance` | `partner {id, name}`, `orders`, `order_value`, `dispatched_value`, `leads_assigned`, `received`, `balance`, `complaints` | `received` and `balance` are all-time, not windowed |
| `/reports/territory-performance?level=district\|taluka` | `territory {id, name}`, `leads`, `won`, `conversion_pct`, `orders`, `order_value` | staff only |
| `/reports/complaints?group_by=type\|status\|severity` | `key`, `count`, `resolved`, `resolved_within_sla_pct`, `response_breaches`; totals carry `refunds {count, amount}` | complaints first submitted in the window |

Example:

```json
{ "data": { "group_by": "source",
  "rows": [ { "key": { "id": "uuid", "label": "WhatsApp" }, "leads": 120, "contacted": 96, "qualified": 60,
              "quoted": 41, "won": 18, "lost": 30, "open": 72, "conversion_pct": "15.0" } ],
  "totals": { "leads": 400, "won": 51, "conversion_pct": "12.8" }, "truncated": false,
  "filters": { "from": "2026-10-01", "to": "2026-10-31", "territory_id": null, "owner_id": null } } }
```

## `GET /leads/{id}/360`

```json
{ "data": { "lead": { "id": "uuid", "inquiry_no": "…", "farmer_name": "…", "mobile": "…", "stage": "won" },
  "related_leads": [ { "id": "uuid", "inquiry_no": "…", "stage": "lost", "relation": "same_mobile" } ],
  "summary": { "quotations": 2, "orders": 1, "order_value": "118000.00", "received": "100000.00",
               "complaints": 0, "visits": 3, "open_tasks": 1, "subsidy_stage": 7 } } }
```

- Tiles across the top. `related_leads` are other leads on the same phone number; call them "same mobile", not "same customer", because farmers share phones.
- The timeline below is the existing `GET /leads/{id}/timeline`. It already shows visits, payments, subsidy stages, orders and complaints.

## Screens

| Screen | Notes |
|---|---|
| Reports home | a card per report the user may open |
| Each report | date range, territory, person, group by; a table and totals; Excel button (disabled on 501) |
| Lead 360° | tiles, related leads, the timeline |

## Defaults the client has not confirmed

- Conversion = leads won ÷ leads created in the period.
- Sales count commercial, industrial, export and subsidised orders only.
- A lead counts for its current owner.
