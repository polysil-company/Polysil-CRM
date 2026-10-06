# Tasks for dealers

> Full spec: FS-037. Off until the admin switches `tasks_for_dealers` on in `/settings`.

```jsonc
// GET /api/v1/tasks/assignees?include_partners=true
{ "data": [ { "id": "uuid", "full_name": "Ravi Patel", "kind": "staff" },
            { "id": "uuid", "full_name": "Bhavesh Shah", "kind": "partner",
              "partner": { "id": "uuid", "name": "Shah Irrigation", "partner_type": "dealer" } } ] }

// POST /api/v1/tasks   { "assigned_to": "<dealer user id>", ... }   as today
// 422 not_assignable | link_not_visible_to_assignee
```

A dealer user sees its own tasks (`GET /tasks?assigned_to=me`, `GET /tasks/{id}`) and completes them
(`POST /tasks/{id}/complete`). Edit, cancel and reopen answer 403 for a dealer.

Screens: a "Dealers" group in the assignee picker when the setting is on; a Tasks page in the
dealer portal with Complete only.
