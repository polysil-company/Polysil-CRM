# Tasks and Planner Contract - `/api/v1/tasks`, `/planner`, `/minutes`

> **Status: specified, being built.** The generated reference will be `backend/docs/api/tasks.md` once the endpoints exist; until then this page is the promise.

## What to build

1. **My day**: today's tasks, and the overdue ones on top.
2. **Team day** (managers): one row per person below them.
3. **Task form**: type, title, due date and time, assignee, and what it is about (a lead, a dealer or an order).
4. **Lead detail, Tasks and meetings tab**, with "Add meeting" (one of the lead's meeting types).
5. **Meeting minutes**: attendees, notes, and action items that become tasks.
6. **Meeting types** in the admin lookups screen.

Dealers get no tasks.

## Tasks

| Call | Notes |
|---|---|
| `POST /tasks {title, task_type, due_at, assigned_to?, lead_id?, partner_id?, sales_order_id?, meeting_type_id?, notes?}` | `task_type`: `call`, `visit`, `meeting`, `followup`, `other`. At most one of the three links. `meeting_type_id` is required for a `meeting` on a lead, and refused otherwise. `assigned_to` defaults to you; offer only people from `GET /tasks/assignees`. `due_at` carries a timezone; a date alone means 18:00 IST |
| `GET /tasks` | filters `assigned_to` (`me` or an id), `status` (repeatable: `open`, `done`, `cancelled`), `task_type`, `lead_id`, `partner_id`, `sales_order_id`, `due_from`, `due_to` (dates), `overdue=true`; keyset paging with `cursor`; `include_total` |
| `GET /tasks/{id}` | the task |
| `PATCH /tasks/{id} {title?, due_at?, notes?, assigned_to?, expected_status?}` | an open task only. Reassigning may answer `422 link_not_visible_to_assignee`: that person cannot open the lead or order |
| `POST /tasks/{id}/complete {outcome, gift_shown?}` | `outcome` required. `gift_shown` only on a meeting |
| `POST /tasks/{id}/cancel {reason}` | `reason` required |
| `POST /tasks/{id}/reopen` | a done task, within 7 days |
| `GET /tasks/assignees` | yourself and the people below you |

A task:

```jsonc
{ "id": "…", "title": "Survey the farm", "task_type": "meeting", "status": "open", "overdue": false,
  "due_at": "2026-10-02T10:30:00+05:30",
  "assigned_to": {"id": "…", "full_name": "Ravi Solanki"}, "assigned_by": {"id": "…", "full_name": "Asha Patel"},
  "lead": {"id": "…", "inquiry_no": "POL/GJ/2026-27/00012", "farmer_name": "…"},   // or null, or {"id", "hidden": true}
  "partner": null, "sales_order": null,
  "meeting_type": {"id": "…", "code": "survey_design", "name": "Survey & Design"},
  "minutes_id": null, "notes": "…", "outcome": null, "gift_shown": null, "cancel_reason": null,
  "completed_at": null, "completed_by": null, "created_at": "…", "updated_at": "…" }
```

- `overdue` is computed by the server; show it, never compute it.
- A `409 task_not_open` after a retried complete means it is already done: treat it as settled.
- `lead: {"id", "hidden": true}` means the lead moved out of your reach; show "lead not visible".

## The planner

| Call | Notes |
|---|---|
| `GET /planner?date=2026-10-02&user_id=` | one person's day (IST): due that day, and open tasks overdue before it (up to 90 days back). `user_id` defaults to you |
| `GET /planner/team?date=&org_unit_id=&cursor=` | one row per active person below you: `due_today`, `done_today`, `overdue`, with name and office; people with no tasks included; 100 a page. `403` for someone with no team |

## Meeting types

`GET /lookups/meeting-types` returns By call, Survey & Design, C & D understanding, Won or wait, Follow-up, and any the admin adds. Admins add and edit them like the other lead lookups.

## Meeting minutes

| Call | Notes |
|---|---|
| `POST /minutes {lead_id or partner_id, task_id?, held_at, attendees: [...], notes, action_items: [{title, assigned_to?, due_at, task_type?}]}` | `held_at` with a timezone, like `due_at`. One save: the minutes and a task per action item. One bad action item refuses the whole save, with `fields.action_items[i]`. An action item is not a meeting. `task_id`: the meeting this records; it is completed if still open |
| `GET /minutes?lead_id=` or `?partner_id=` | newest first |
| `GET /minutes/{id}` | with each action item's current task, so show "2 of 3 done" |

Minutes are for staff; a dealer never sees them.

## People leaving (the users screens)

| Call | What changes |
|---|---|
| `POST /users/{id}/handover` | also moves every open task to the receiver. The result gains `tasks_moved` |
| `PATCH /users/{id} {"is_active": false}` | `422` with `fields.is_active` while the person has open tasks. Offer the handover |
| `DELETE /users/{id}` | `422` with `fields.open_tasks` while the person has open tasks |

A person moved to another office takes their open tasks with them. Nothing to build for that.

## Not yet

- GPS check-in, photos, the team map (Phase 2).
- A WhatsApp when a task is assigned.
- Tasks for dealers.
