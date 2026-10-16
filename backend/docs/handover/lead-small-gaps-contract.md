# QR code edit, dormant leads, and the office on assign

> Three small lead changes. Full spec: FS-035. All additive except one behaviour change on assign.

## Edit a QR code

```jsonc
// PATCH /api/v1/lead-qr-codes/{id}      (leads.edit, Idempotency-Key)
{ "label": "Shah Irrigation counter", "campaign": null, "partner_id": "uuid",
  "territory_id": "uuid", "is_active": false }          // any subset; null clears (not label)
// 200 { "data": QrCode }      same shape as the list item
// 404  not yours to edit
// 422  fields: partner_id "not found" | territory_id "choose a territory in your area" | body "nothing to change"

// GET /api/v1/lead-qr-codes?active=true|false        new optional filter
```

The code and its URL never change, so printed codes keep working. A new dealer applies to
new leads only. A switched-off code's link answers `GET /public/lead-form?qr=` with 404:
show the plain form. A submission that still names it becomes a website lead.

## Dormant leads

A lead with no activity for 60 days (admin setting) moves to `dormant` overnight. It is not
swept while it has an open task or a quotation that is sent, viewed or in negotiation.

```jsonc
// Lead gains:  "dormant_from_stage": "qualified" | null      the stage it returns to

// wake it up: back to dormant_from_stage
// POST /api/v1/leads/{id}/reopen        { "note": "Farmer called back" }     (body optional)

// or close it
// POST /api/v1/leads/{id}/transition    { "to_stage": "lost", "lost_reason_id": "uuid" }
```

Timeline: `lead.stage_changed` with `{ "from": "qualified", "to": "dormant", "reason":
"no_activity", "days": 60 }`, by "System". A dormant lead can still be edited, assigned,
noted and given tasks; quotations refuse it (`422 lead_not_open`). A note does not wake it.

The setting: `dormant_after_days` in `GET/PATCH /api/v1/lookups/scoring` (`masters.edit`).

## Assign moves the office

`POST /api/v1/leads/{id}/assign` is unchanged in shape. The lead's office now follows the new
owner: their own sales office, or the office covering the lead's territory when they have
none. After an assign, re-read `owner_org_unit` from the response.

## Screens

- QR codes: Active/Off chip and filter; Edit (label, campaign, dealer, territory, active).
- Lead detail when `stage = "dormant"`: banner "No activity for 60 days. Was: <dormant_from_stage>",
  buttons Reopen and Mark lost.
- Admin lead settings: `dormant_after_days` beside the scoring numbers.
