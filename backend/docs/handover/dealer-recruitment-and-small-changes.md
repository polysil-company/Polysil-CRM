# Dealer recruitment, and five small changes from the client's sheet

Full contracts: `docs/api/dealer-applications.md`, `docs/api/dashboard.md`, `docs/api/orders.md`, `docs/api/leads.md`.

## Dealer recruitment (sheet item 8)

### Staff screens

| Call | What it does |
|---|---|
| `POST /dealer-applications` `{firm_name, contact_name, mobile, territory_id, lead_id?}` | start one. Answers `apply_url`: show it with a Copy and a Share on WhatsApp button. **It is shown only now** (and after a renew) |
| `GET /dealer-applications?status=&q=` | the list |
| `GET /dealer-applications/{id}` | every field, `missing` (what is still needed), `can` (edit, decide, withdraw, renew) |
| `PATCH /dealer-applications/{id}` | staff fill fields for the applicant |
| `POST .../submit`, `.../withdraw {remark}`, `.../link` (a new link; the old one stops) | |
| `POST .../decision {decision: approve\|reject\|return, remark, parent_id?, code?}` | approve creates the dealer and its login; `parent_id` is a distributor picker (or none: directly under Polysil); `code` blank: automatic |
| `GET /documents?record_type=dealer_application&record_id=` and `POST /documents` | the documents, as on any record |

Show Decide only when `can.decide`. Errors: `409 mobile_in_use`, `409 application_open`, `409 already_decided`, `422 application_incomplete` (its `fields` name what is missing).

### The applicant's page (public, mobile first): `/dealer-apply/<token>`

1. `GET /public/dealer-apply/{token}`: without a session, the firm name, the masked mobile, `status`, `missing`. Show "Verify your mobile".
2. `POST .../verify` (a WhatsApp code), then `POST .../verify/check {code}` answers `session`. Send it as `X-Apply-Session` on every later call (2 hours).
3. The form: firm type, GST registered yes or no, GSTIN with a "Check GSTIN" button (`GET .../gstin/{gstin}`: `valid`, `pan`; `lookup` is `unavailable` for now, so the applicant types the names), PAN, address, pincode, bank account name, number and IFSC, and the optional fields. `PATCH .../{token}` saves.
4. Documents: `POST .../documents` (multipart: `doc_type` gst_certificate, pan_card, cancelled_cheque, shop_photo, shop_licence or other with `name`; `file`). `DELETE .../documents/{id}` removes one of theirs.
5. `POST .../submit`. Then a "Submitted, we will be in touch" page.

A returned application shows the manager's `remark`; the applicant fixes it and submits again. `403 no_session` means verify again.

## Five small changes

| Item | Change |
|---|---|
| Dashboard: area by system | `area_by_system: [{system, name, leads, hectares}]` on `GET /dashboard/overview` |
| Dashboard: target vs orders | `targets_by_month: [{month, target, achieved}]`, 6 months, oldest first; null without a targets permission |
| Order filters | `GET /orders` (and stats, export): `territory_id` (a comma list; a state selects its districts) and `owner_org_unit_id`, as on Leads |
| Land in hectares | leads take and return `land_hectares`; `land_acres` still works (converted). Ask for hectares on the forms |
| Lead export | adds State and Land (ha) columns |

## Also from this round

The replacement order chain and documents are in handover 60; group chats in 59.
