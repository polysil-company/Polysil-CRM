# Subsidy Applications Contract - `/api/v1/subsidy-applications`

> **Status: built and on staging.** The generated reference is `backend/docs/api/subsidy-applications.md`. This page says what to build and the things the reference cannot show.

## What to build

1. **"Start subsidy application"** on a lead. Show it when the lead's inquiry type is `subsidised`, its stage is `qualified`, `quoted`, `negotiation` or `won`, and its system is drip, mini sprinkler or sprinkler. It reuses the subsidy calculator screen and adds one pick: the farmer's category.
2. **Applications worklist:** number, farmer, current stage, days in stage, Reg. No. Filters: status, stage, search.
3. **Application page:**
   - the header: number, Reg. No., status, farmer, lead link, figures (total cost, subsidy, farmer share), category;
   - the stage history, oldest first;
   - "Record stage": a form built from the stage's field list;
   - the document checklist, with uploads;
   - "Download PIMS sheet";
   - "Cancel application", with a reason.
4. **A tab on the lead:** its application, if any.

Not yet: the printed GGRC documents (the application form, undertakings, the quotation in GGRC's format). Dealers have no access to any of this.

## Who sees what

| Role | Sees | Can start, record, upload, cancel |
|---|---|---|
| Field Officer | their own leads' applications | yes |
| District / State Manager | their office tree | yes |
| State Co-ordinator | every application in their state | yes |
| Regional Manager, Account Manager, Board | view only (their tree, or all) | no: hide the buttons |
| Admin-Sales, MD/CEO | all | yes |
| Dealers | nothing: every route answers `403` | - |

A view-only user gets `403` on an upload or a stage. Hide those controls when the user lacks `subsidy.create` and `subsidy.edit` (from `/auth/me` permissions).

## The flow

Start: the lead moves to `won`, and the application opens at stage 4 ("Application in process"), dated today.

Then any stage, in any order, as things happen at GGRC (stages 4 to 17). Going back, or recording the current stage again, needs a remark.

The application closes itself (`full_fp_received`) when every payment amount entered at stage 16 has its received date at stage 17. Nothing needs to be clicked. A closed application takes no more entries.

Cancel (`cancelled`) frees the lead: it can be started again.

## Starting an application

`POST /subsidy-applications`, with `Idempotency-Key`:

```jsonc
{
  "lead_id": "…",
  "category_code": "small_farmer",           // from the calculation's categories[].code
  "calculation": { /* exactly the body sent to POST /subsidy/calculate */ },
  "survey_no": "112/2"                        // optional
}
```

- Run `POST /subsidy/calculate` first and let the user pick a category from the answer. Offer only categories with `applicable: true` on **every** crop.
- The backend runs the calculation again and stores it. The figures shown later are the stored ones, never recomputed. `GET /{id}/calculation` returns the stored calculation in the calculator's shape.
- `calculation.system_type` must be the lead's system.

Refusals, all `422` unless marked:

| Code or field | Meaning |
|---|---|
| `lead_not_subsidised` | the lead's inquiry type is not subsidised |
| `lead_not_forwardable` | the lead is not qualified, quoted, in negotiation or won |
| `lead_system_not_subsidised` | the lead's system has no subsidy calculation |
| `already_forwarded` | the lead already has a live application |
| `category_code` | not a category of this calculation, or it does not apply on some crop (the message says which) |
| `calculation.<field>` | the calculator's own errors, under `calculation.` |
| `404` | the lead is not in your scope |

## Recording a stage

Build the form from `GET /subsidy-stages`. Never hard-code the stages; they are data. Each stage has `seq`, `code`, `name` and `fields: [{key, label, type, required}]`, where `type` is `date`, `amount` or `text`.

`POST /subsidy-applications/{id}/stages`, with `Idempotency-Key`:

```jsonc
{
  "stage_code": "payment_received",
  "occurred_on": "2026-08-14",               // the business date; not after today in India
  "values": {"pfms_received": "2026-08-14", "state_share_received": null},
  "remark": "PFMS credited"                  // required going back, or for the same stage
}
```

**Every value is a string, or null:**
- dates as `YYYY-MM-DD`;
- amounts as decimal strings: `"1250.50"`, not `1250.5`;
- text as typed, up to 500 characters.

A JSON number or `true` is a `422`. Null, or an empty string, clears the field: an emptied date input can send `""`.

Refusals: `422` on `values.<key>` (wrong type, unknown key, negative, more than two decimals, `1e12` or more, a future date), `occurred_on`, `stage_code` or `remark`. `409 status_changed`: the application is closed or cancelled; reload.

The latest value of each field wins, across all entries. The application's Reg. No. is the latest one entered at stage 4; entering it blank clears it.

## Documents

| Call | Notes |
|---|---|
| `GET /subsidy-document-types` | the 20-item checklist. None is required |
| `GET /{id}/documents` | the checklist, each item with its files |
| `POST /{id}/documents` | `multipart/form-data`: `file` and `document_type` (a checklist `code`). PDF, JPEG, PNG, WebP or HEIC, up to 10 MB, judged by content. Up to 40 files per application. `201`, or `200` with the existing file if the same file was added before |
| `GET /{id}/documents/{doc_id}` | `{url, expires_at}`: a 10-minute link. Put `url` in an `<img>` or open it; never fetch it with the bearer token |

Upload refusals:

| Response | Meaning |
|---|---|
| `422 too_many_documents` | 40 files already |
| `422 attachment_type` | not an allowed file type |
| `422` on `file` | empty |
| `422` on `document_type` | not on the checklist |
| `413` | over 10 MB |
| `403` | view-only user |
| `409 status_changed` | the application is cancelled |
| `503 storage_unavailable` | retry later |

Staging has file storage since 1 Oct. `503 storage_unavailable` can still happen if storage is unreachable: show "Files cannot be stored right now" and keep the form usable.

## The PIMS sheet

`GET /{id}/pims.xlsx` is a file download (`Content-Disposition: attachment`). Fetch it with the bearer token and save the blob; a plain link cannot carry the header. The columns are CostType, Crop, ItemCode, Item, Size, Unit, Rate, Quantity, Amount, Remark.

## The shape

```jsonc
{
  "id": "…", "application_no": "SA/GJ/2026-27/00001", "reg_no": "GGRC/24/001",
  "status": "open",                                   // open | full_fp_received | cancelled
  "current_stage": {"seq": 5, "code": "technical_in_process", "name": "Technical in process", "since": "2026-08-10"},
  "scheme": "GGRC", "system_type": "drip",
  "category": {"code": "small_farmer", "name": "Small farmer", "pct": "90"},
  "lead": {"id": "…", "inquiry_no": "POL/GJ/2026-27/00078"},
  "farmer_name": "Rameshbhai Patel", "mobile": "+919812345678", "village": "Anand", "survey_no": "112/2",
  "territory": {"id": "…", "name": "Anand", "level": "district"},
  "partner": null,                                    // or {"id", "name"}
  "total_area": "2.250", "group_total_area": null,
  "figures": {"total_cost": "95000.75", "subsidy": "70000.50", "farmer_share": "17500.25"},
  "owner": {"id": "…", "full_name": "…"},
  "owner_org_unit": {"id": "…", "name": "Anand office"},
  "documents": {"uploaded": 3, "listed": 20},         // checklist items with a file / active items
  "ageing": {"days_in_stage": 4, "days_since_inward": 19},
  "full_fp_received_on": null,
  "created_at": "…",
  "cancellation": null                                // or {"reason"}
}
```

Money and areas are decimal strings; show them as they are. `days_since_inward` counts from the App. Inward Date entered at stage 4, or from the first stage-4 entry. It is null only before any stage-4 entry.

The list is `GET /subsidy-applications?status=&stage=&q=&limit=&cursor=`, newest first: `{data: [...], meta: {next_cursor}}`. `q` matches the application number, the Reg. No. or the farmer's name.

## On the lead's timeline

The lead's history shows `subsidy.created`, `subsidy.stage_recorded` (with `direction`: forward, same or back), `subsidy.closed`, `subsidy.cancelled` and `subsidy.document_added`. Starting an application also writes `lead.stage_changed` to `won`, with `via: "subsidy_application"`.

## Not decided yet

These are our readings of the client's material. Each may change once the client answers:
- the stage list and the checklist are fixed for now; an admin screen comes later;
- no document is required at any stage;
- a closed application cannot be corrected;
- nobody is notified of a stage change;
- the PIMS layout follows the one sample the client gave.
