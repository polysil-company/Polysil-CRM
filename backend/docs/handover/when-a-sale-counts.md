# When an order counts as a sale

> Full spec: FS-026. All additive. No new endpoint.

## The setting (admin)

One more row in the settings list (`GET /api/v1/settings`, `PATCH /api/v1/settings`):

```jsonc
{ "key": "sale_counted_at", "kind": "choice", "value": "approval",
  "allowed": ["submission", "approval", "dispatch", "payment"],
  "description": "When an order counts as a sale in reports and targets." }
```

| Value | An order counts on |
|---|---|
| `submission` | the day it was submitted |
| `approval` (default) | the day it was approved |
| `dispatch` | the day its last line shipped |
| `payment` | the day the receipts reached what is owed |

Suggested label: "When an order counts as a sale". Add a note under it: "Changing this
recalculates reports and targets for every month."

Drafts (rejected or amended orders), cancelled orders, and orders closed short with nothing
shipped never count.

## What it changes

| Where | Change |
|---|---|
| Every `GET /reports/*` | `data.filters.sale_counted_at` is the mode the figures used |
| `GET /targets/achievement` | new `data.filters.sale_counted_at` |
| `GET /orders/{id}` | new `fully_dispatched_at`: null until the order is dispatched, or closed short after a dispatch |

Show one small line on each report and on achievement: "Sales counted at: approval".
Order counts and order values in the reports, the dealer and territory reports, the lead
360's order count and achievement all follow the setting. Lead, task, visit and complaint
figures do not change. A dealer's received and balance stay all-time.
