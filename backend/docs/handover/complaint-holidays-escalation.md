# Complaint holidays and escalation

> Full spec: FS-028. All additive.

## Holidays (admin)

Complaint targets count working hours, Monday to Saturday, 09:30 to 18:30 IST. A holiday counts like a Sunday.

```jsonc
// GET /api/v1/holidays?year=2026            any signed-in user
{ "data": [ { "day": "2026-11-08", "name": "Diwali" } ] }

// POST /api/v1/holidays                      masters.edit, Idempotency-Key
{ "day": "2026-11-08", "name": "Diwali" }
// 201 the holiday
// 409 holiday_exists
// 422 holiday_in_past (today or earlier, IST) or holiday_sunday

// DELETE /api/v1/holidays/2026-11-08         masters.edit, Idempotency-Key
// 204; 409 holiday_in_past
```

Suggested screen: a list by year with "Add holiday" (date and name) and a remove button on future days only. Note under it: "A new holiday applies to complaints submitted after it is added."

## Escalation (admin setting)

One more row in `GET/PATCH /api/v1/settings`:

```jsonc
{ "key": "complaint_escalation", "kind": "choice", "value": "bell",
  "allowed": ["off", "bell"],
  "description": "When a complaint misses its response or resolution target: do nothing, or ring the bell for its owner and the managers handling it." }
```

Suggested label: "Complaint escalation". Options: "Off", "Ring the bell".

## What staff see

| Where | What |
|---|---|
| Bell | new kind `complaint_escalated`: "Complaint Poly/Comp./2026-27/GJ/07 missed its response target" (or "resolution target"), linking to the complaint |
| `GET /complaints/{id}` | `response_escalated_at`, `resolution_escalated_at`: null, or when it was escalated. Staff only; always null for a dealer |
| Timeline | a `complaint.escalated` event by System, payload `{target, due_at}` |

Show "Response target missed" or "Resolution target missed" on the complaint when the field is set.

Dealers get no bell. They can see the timeline event, which names no person.
