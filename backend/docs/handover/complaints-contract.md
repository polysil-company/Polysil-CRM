# Complaints Contract - `/api/v1/complaints`

> **Status: specified, being built.** The generated reference will be `backend/docs/api/complaints.md` once the endpoints exist; until then this page is the promise.

## What to build

1. **Complaint form** (staff and dealers): type, severity, contact name and mobile, where the material is installed (territory), optionally the lead or order it is about, the products with supplied and defective quantities, the challan number and supply date, photos and documents. Save as a draft, then Submit.
2. **Complaints list**: filters by status, type, severity, dealer, "breached", "no owner"; the number, contact, age and a red mark when a target is missed.
3. **My queue** (managers and QC): what is waiting for my check or my QC verdict.
4. **Complaint detail**: header, products, attachments, the manager's check, the QC verdict, the targets with their due times, the timeline. Show only the buttons in `can`.
5. **Check dialog** (managers): approve or return, a remark, optionally a new severity and an owner.
6. **QC dialog** (QC): approve or reject, a remark, the sample received, tested and field-visit dates.
7. **Admin**: the complaint types (like the lead lookups) and the response and resolution targets.
8. **Tabs on a lead and an order**: their complaints.

Not yet: replacement orders, refunds, closing a complaint. An approved complaint waits in `qc_approved`.

## The flow

`draft` → Submit → `submitted` (numbered `Poly/Comp./2026-27/GJ/01`) → manager check:
- **return**: back to `draft` with the manager's remark; the raiser fixes it and submits again;
- **approve**: `under_qc` → QC verdict: `qc_approved` or `qc_rejected` (closed).

The raiser can cancel a `draft` or `submitted` complaint with a reason.

## Complaints

| Call | Notes |
|---|---|
| `POST /complaints` | `{complaint_type_id, severity?, description, contact_name, contact_mobile, territory_id, partner_id?, lead_id?, sales_order_id?, dc_no?, supply_date?, reg_no?, pims_no?, sample_courier_date?, sample_courier_detail?, lines: [{product_id, supplied_qty, defective_qty, failure_frequency?, remark?}]}`. `201` draft. 1 to 20 lines, each product once, `defective_qty` not more than `supplied_qty`. A dealer does not send `partner_id`; it is always their own. Linking an order fills the challan and supply date |
| `GET /complaints` | `status`, `complaint_type_id`, `severity`, `partner_id`, `lead_id`, `sales_order_id`, `owner=none`, `breached=true`, `awaiting=me`, `q` (number, contact name or mobile), `limit`, `cursor` |
| `GET /complaints/stats` | counts by status, breached, and `storage_available` (hide the upload button when false) |
| `GET /complaints/{id}` | the shape below |
| `PATCH /complaints/{id}` | a draft only; header fields. `409 complaint_not_draft` if it moved on |
| `PUT /complaints/{id}/lines` | a draft only; replaces the lines, 1 to 20 |
| `DELETE /complaints/{id}` | a draft never submitted |
| `POST /complaints/{id}/submit` | `{}`. `422 missing_for_submit` (the challan number or supply date, in `fields`), `422 nothing_defective` (every line has 0 defective), `422 no_checker` (nobody may check it; tell the user to contact the admin) |
| `POST /complaints/{id}/check` | `{decision: "approve" or "return", remark, severity?, owner_user_id?, internal_note?}`. `severity` and `owner_user_id` only with approve; offer owners from `GET /complaints/{id}/assignees` |
| `POST /complaints/{id}/qc` | `{verdict: "approved" or "rejected", remark, sample_received_on?, tested_on?, field_visit_on?, internal_note?}` |
| `POST /complaints/{id}/cancel` | `{reason}` |
| `GET /complaints/{id}/assignees` | the owner picker in the check dialog |
| `GET /complaints/{id}/timeline` | events, newest first |

All mutations take `Idempotency-Key`. Dates are `YYYY-MM-DD` and cannot be after today; a sample cannot arrive before the supply date. `409 status_changed` means someone acted first: reload.

## Attachments

| Call | Notes |
|---|---|
| `POST /complaints/{id}/attachments` | `multipart/form-data` with `file` and `kind` (`photo`, `document`, `challan`). Up to 10 MB; JPEG, PNG, WebP, HEIC or PDF, judged by the file's content, not its name. Up to 10 per complaint. `201`, or `200` with the existing one if the same file was already added. `413` too large, `422 attachment_type`, `422 too_many_attachments`, `503 storage_unavailable` (retry later) |
| `GET /complaints/{id}/attachments/{attachment_id}` | `{url, expires_at}`: a link valid for 10 minutes. Put `url` in an `<img>` or open it for a download; never fetch it with the bearer token. Each attachment has `preview`: false for HEIC |
| `DELETE /complaints/{id}/attachments/{attachment_id}` | in a draft: the uploader or an editor; after submit: the uploader only |

Uploads are allowed while the complaint is a draft or submitted; QC may add while `under_qc`. HEIC (iPhone) photos are stored but cannot be previewed: show a file icon.

## The shape

```jsonc
{
  "id": "…", "complaint_no": "Poly/Comp./2026-27/GJ/01", "status": "submitted",
  "complaint_type": {"id": "…", "code": "dripline", "name": "Dripline / Lateral / PVC"},
  "severity": "medium",
  "description": "Laterals cracking within two months",
  "contact_name": "Kiritbhai Shah", "contact_mobile": "+919876543210",
  "territory": {"id": "…", "name": "Vadod"},
  "partner": {"id": "…", "name": "Shah Irrigation", "partner_type": "dealer"},
  "lead": {"id": "…", "inquiry_no": "…", "farmer_name": "…"},     // or null, or {"id", "hidden": true}
  "sales_order": {"id": "…", "order_no": "SO/…"},                 // or null, or {"id", "hidden": true}
  "dc_no": "DC-4471", "supply_date": "2026-07-14", "reg_no": null, "pims_no": null,
  "sample_courier_date": null, "sample_courier_detail": null,
  "lines": [{"id": "…", "product": {"id": "…", "description": "16mm dripline"}, "uom": "m",
             "supplied_qty": "2000", "defective_qty": "340", "failure_frequency": "every 3 to 4 m", "remark": null}],
  "attachments": [{"id": "…", "kind": "photo", "filename": "lateral.jpg", "content_type": "image/jpeg",
                   "size_bytes": 812345, "uploaded_by": {"id": "…", "full_name": "…"}, "uploaded_at": "…"}],
  "check": {"decision": "approve", "remark": "…", "by": {"id": "…", "full_name": "…"}, "at": "…"},   // since the latest submit, or null
  "quality": {"verdict": "approved", "remark": "…", "sample_received_on": "…", "tested_on": "…",
              "field_visit_on": null, "by": {…}, "at": "…"},                                       // or null
  "cancellation": {"reason": "…", "by": {"id": "…", "full_name": "…"}, "at": "…"},   // or null
  "sla": {"policy": "set", "response_due_at": "…", "responded_at": null, "response_breached": false,
          "resolution_due_at": "…", "resolved_at": null, "resolution_breached": false},            // null before the first submit
  "submit_count": 1,
  "owner": {"id": "…", "full_name": "…"},            // or null: "no owner yet"
  "owner_org_unit": {"id": "…", "name": "…"},
  "raised_by": {"id": "…", "full_name": "…"},
  "can": {"edit": true, "submit": true, "check": false, "qc": false, "cancel": true, "delete": true},
  "created_at": "…", "updated_at": "…", "submitted_at": null
}
```

- Quantities are decimal strings.
- `sla.policy` is `none` when no target applies. Show "no target", never red.
- A dealer sees each remark but not who decided (`by` is null), and `internal_note` is always null for a dealer.
- For staff, `check` and `quality` also carry `internal_note`.

## Targets

`GET /complaint-sla-policies` lists the response and resolution targets, in working hours (Monday to Saturday, 09:30 to 18:30), by severity. `POST /complaint-sla-policies {severity, complaint_type_id?, response_hours, resolution_hours, business_hours_only, effective_from}` sets a new target from a date. Admin only. Today's numbers are stand-ins: high 4 h / 18 h, medium 8 h / 27 h, low 9 h / 45 h.

## Messages

On submit and on each decision, the contact gets a WhatsApp, once the owner creates the two templates in 11za. Nothing to build on the screen.
