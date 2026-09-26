# Quotations API Contract - `/api/v1/quotations` and `/public/q`

> **Status: shipped.** The generated contract is `backend/docs/api/quotations.md` and `backend/docs/api/public.md`, which is the record; this document is the context around it and matches it. The shapes
> below are the contract to build against, the same way `13-Leads-API-Contract.md`
> was before leads shipped. Once the endpoints exist, the generated API doc
> (`backend/docs/api/quotations.md`) supersedes this file's endpoint section:
> the generated doc becomes the record, this stays the promise it was checked
> against. Anything that changes between now and then is additive or announced.
> Companions: `13-Leads-API-Contract.md` (the lead a quotation hangs off) ·
> `17-Products-and-Pricing-Handover.md` (the product picker and the live preview
> this builds on) · `04-Permissions-RBAC.md` (who sees what).

---

## What this is

A field officer turns a qualified lead into a priced, taxed, numbered document,
sends it to the farmer as a PDF over a link, and sees whether it was opened. The
customer's answer is recorded on the same row: accepted, rejected, or "let us
talk", which becomes a new version. Every version stays. The lead moves with the
document, and `won` becomes reachable for the first time.

**The arithmetic already exists.** `POST /pricing/quote-lines` prices a basket
without saving anything; the builder screen calls it on every change for live
totals. A quotation is the save of that preview, the freeze, the number, the PDF
and the lifecycle around it. The server re-prices on every save and refuses with
`409 rate_changed` if a price or tax moved since the preview, so the screen never
saves a figure the user did not see.

---

## 1. Conventions

Everything in `13-Leads-API-Contract.md` §1 applies, plus:

| | |
|---|---|
| Money and rates | decimal **strings**. Amounts have two decimals (`"1667.50"`), rates and percentages three (`"2.500"`, `"10.000"`). Never compute a total on the screen: every figure the document prints is in the response |
| Idempotency | `Idempotency-Key` required on every POST, PATCH, PUT and DELETE |
| `expected_status` | every mutation on an existing quotation accepts it; `409 status_changed` when the row has moved under you. Send the status you rendered |
| Pagination | keyset, as on `GET /leads`, with the same opt-in `?include_total=true` and `meta.total_capped` |
| A quotation outside your scope | `404`, not `403`. It is not there |
| The number | **a draft has no number.** `quote_no` is `null` until the quotation is sent; show "Draft". A revision inherits its predecessor's number with the next `version` |

---

## 2. The lifecycle, and the lead beside it

```
draft ──send──► sent ──first open of the PDF──► viewed
                 │  │                              │
                 │  ├──► negotiation ◄─────────────┤
                 │  │        │                     │
                 │  ▼        ▼                     ▼
                 │  accepted / rejected / expired (nightly, after valid_until)
                 │
                 └──► POST /revise from sent, viewed, negotiation, rejected, expired
                      → a new draft, version n+1, same number
                      → sending it marks version n "superseded" (a flag, not a status)
```

| Event | The lead moves |
|---|---|
| send | `qualified -> quoted` |
| transition to `negotiation` | `quoted -> negotiation` |
| transition to `accepted` | `-> won` |
| `rejected`, `expired` | nothing. The officer marks the lead lost with a reason, or revises |

A quotation can only be created on a lead in `qualified`, `quoted`,
`negotiation` or `won` (a second unit on a deal already won; nothing moves). On a lead that is `new` or `contacted` the API answers `422
lead_not_qualified`; disable the button and say why. On a lost, merged or
deleted lead every send, negotiation and acceptance answers `422 lead_not_open`
naming the stage; a lost lead is reopened first (`POST /leads/{id}/reopen`).

`superseded` is not a status. It is `superseded_by: { id, version }` on the older
version, set when the newer one is sent. A superseded row keeps its status, its
PDF and its link, and refuses every transition with `409 quotation_superseded`.
Render it muted with a "superseded by v2" overlay.

---

## 3. The document shape

`GET /quotations/{id}`, and the body of every mutation's 200 / 201:

```jsonc
{ "data": {
    "id": "uuid", "quote_no": "QT/GJ/2026-27/00001", "version": 1,   // quote_no null while draft
    "status": "sent", "sales_type": "commercial", "source": "internal",
    "lead": { "id": "uuid", "inquiry_no": "POL/GJ/2026-27/00123", "stage": "quoted" },  // null if the lead is deleted or outside your lead scope
    "party": { "name": "Rameshbhai Patel", "mobile": "+919876543210",
               "address": "Vadod, Anand, Gujarat", "gstin": null },
    "partner": null,                                    // { id, name, partner_type } when the sale goes through a dealer
    "owner": { "id": "uuid", "full_name": "Kiran Shah" },   // the lead's owner; null while the lead is unassigned
    "owner_org_unit": { "id": "uuid", "name": "Anand" },
    "territory": { "id": "uuid", "name": "Anand", "level": "district" },
    "seller_gstin": { "id": "uuid", "gstin": "24AAACP1234A1Z5", "legal_name": "Polysil Irrigation Systems Pvt Ltd", "state": "GJ" },
    "place_of_supply": { "territory": { "id": "uuid", "name": "Anand", "level": "district" }, "state": "GJ" },
    "intra_state": true,
    "price_effective_date": "2026-10-01",
    "price_list": { "id": "uuid", "name": "GJ 2026-27" },   // null when lines drew from more than one list
    "price_list_ids": ["uuid"],
    "lines": [
      { "line_no": 1, "product_id": "uuid",
        "description": "UPVC PIPE 90 MM 4 KG/CM2 CLASS - 2 IS: 4985", "hsn_code": "3917", "uom": "MTR",
        "qty": "18.000", "rate": "103.19", "gross": "1857.42",
        "discount_pct": "10.000", "discount1_amt": "185.74", "after_discount1": "1671.68",
        "discount2_pct": "5.000",  "discount2_amt": "83.58",  "after_discount2": "1588.10",
        "discount3_pct": "0.000",  "discount3_amt": "0.00",
        "discount": "269.32",                                // the three amounts summed
        "taxable": "1588.10",
        "gst_slab": "5.000", "cgst_rate": "2.500", "sgst_rate": "2.500", "igst_rate": "0.000",
        "cgst": "39.70", "sgst": "39.70", "igst": "0.00", "total": "1667.50",
        "price_list_id": "uuid", "price_list_item_id": "uuid", "gst_rate_id": "uuid",
        "provisional_fields": ["rate"] } ],
    "totals": { "gross": "1857.42", "discount": "269.32", "taxable": "1588.10",
                "cgst": "39.70", "sgst": "39.70", "igst": "0.00", "total": "1667.50" },
    "is_provisional": true,                    // any line carries a stand-in rate or slab: show the banner the PDF shows
    "warnings": ["provisional_pricing: 1 of 1 lines use stand-in rates or tax slabs"],
    "terms": "Prices ex-works. Delivery in 7 days.",
    "valid_until": "2026-11-06", "sent_at": "...", "viewed_at": null, "open_count": 0,
    "accepted_at": null, "rejected_at": null, "decided_by": null, "decision_remark": null,
    "supersedes": null, "superseded_by": null,       // { id, version } when set
    "share_url": "https://<your app>/q/<token>",     // present on every read once sent
    "pdf_state": "pending",                          // pending | ready | failed; null on a draft
    "pdf_error": null,
    "created_at": "...", "created_by": { "id": "uuid", "full_name": "Kiran Shah" }, "updated_at": "..." } }
```

**The three discounts.** Each tier is a percentage of the running balance, and
each amount is rounded to the paisa before the next tier applies. `discount_pct`
is tier one's percentage; `discount` is the sum of all three amounts, so do not
check `gross × discount_pct / 100 == discount` on a multi-tier line. The columns are
the client's own sheet's columns: `1st Disc.(%)`, `1st Disc.(Amt.)`, `Amt. After
1st Disc.`, and so on, then the total discount, then GST. Show them in that order.

`warnings` are `code: sentence`; split on the first colon, switch on the code,
show the sentence. Codes you will see: `provisional_pricing`, `future_price_date`,
`mixed_price_lists`, `repriced` (on a revision), `discontinued_products` (on send
or a revision: a product on the document is no longer sold; informational).

---

## 4. Endpoints

### `POST /quotations` - create a draft

```jsonc
{ "lead_id": "uuid",
  "sales_type": "commercial",                     // defaults to the lead's inquiry_type; commercial | industrial
  "partner_id": null,                             // OMIT the field for the lead's assigned partner; send null for a direct sale at the farmer tier
  "place_of_supply_territory_id": null,           // defaults to the lead's territory
  "seller_gstin_id": null,                        // defaults to the registration in force
  "price_effective_date": null,                   // defaults to today; a future date is allowed and warns
  "party": { "name": "...", "mobile": "+91...", "address": "...", "gstin": null },   // defaults from the lead; name 1..200, address up to 500
  "terms": "...",                                 // optional, up to 2000 characters, printed at the foot
  "lines": [                                      // 0 to 200; an empty draft is allowed
    { "product_id": "uuid", "qty": "18",
      "discount_pct": "10.000", "discount2_pct": "5.000", "discount3_pct": "0.000",
      "price_list_item_id": "uuid", "gst_rate_id": "uuid" } ] }   // what the preview returned; optional
```

Pass `price_list_item_id` and `gst_rate_id` from the preview on every line. If
either no longer matches what the server resolves, the whole save is refused:

```jsonc
// 409
{ "error": { "code": "rate_changed",
             "message": "Prices or tax changed since the preview. Review the new figures and save again.",
             "fields": { "lines[0].rate": "103.19 -> 108.35", "lines[2].gst_slab": "5.000 -> 12.000" } } }
```

Show the changed lines from `fields`, re-run the preview, let the user save again
**with a new `Idempotency-Key`**: a refusal is stored against the key it was made
with, and a retry with the same key replays the 409. Omit the two ids and the save
takes whatever resolves.

`201` with the document. Errors: `lead_not_qualified`, `lead_not_open`,
`sales_type_unsupported` (`export`, `marketing`, `sample`, `subsidised` are refused
until their rules are answered; the message names the question), `rate_changed`,
and every pricing error the preview can return (`product_inactive`,
`product_not_priced`, `product_missing_tax_rate`, `qty_not_multiple`,
`line_total_too_large`, ...), each naming `lines[i].field`.

### `GET /quotations` - the list

Query: `lead_id`, `status`, `sales_type`, `owner` (`me` or a user id),
`partner_id`, `q` (number, party name or mobile), `from`, `to` (created date),
`current_only` (default `true`: hides superseded versions), `limit` (1 to 100,
default 25), `cursor`, `include_total`. Newest first.

`lead_id` also returns quotations on leads merged into that one.

Rows are the header without lines: id, quote_no, version, status, sales_type,
lead, party name and mobile, partner, owner, totals, is_provisional, valid_until,
sent_at, viewed_at, pdf_state, superseded_by, created_at.

### `GET /quotations/{id}`

The document. `404` outside scope.

### `PATCH /quotations/{id}` - change a draft's header

`{ "party": {...}, "terms": "...", "price_effective_date": "...", "expected_status": "draft" }`:
any of `sales_type`, `partner_id`, `place_of_supply_territory_id`,
`seller_gstin_id`, `price_effective_date`, `party`, `terms`, plus
`expected_status`. Every change re-prices the lines, so the response is the whole
document again. `409 quotation_not_draft` on anything but a draft.

### `PUT /quotations/{id}/lines` - replace a draft's lines

`{ "lines": [ ...same line shape... ], "expected_status": "draft" }`. Array order
is `line_no`. Same `rate_changed` contract as create. Zero lines is allowed.

### `POST /quotations/{id}/send`

```jsonc
{ "channel": "whatsapp",           // whatsapp | none. none: no message; the officer shares the link himself
  "expected_status": "draft" }
```

The message goes to `party.mobile`, always. To send to another number, change
the party first.

`200` with the document, now carrying `quote_no`, `status: sent`, `sent_at`,
`valid_until` (45 days), `share_url`, and **`pdf_state: pending`**. The PDF is
rendered by a background worker within seconds; poll `GET /quotations/{id}` (or
refresh) until `pdf_state` is `ready`. The WhatsApp message goes out only once
the PDF exists, so the farmer never opens a link whose document is not there.

Errors: `discount_approval_required` (the discount is above the owner's limit;
request approval first, see below), `approval_pending`, `quotation_not_draft`,
`no_lines`, `rate_changed` (a price or tax moved under the draft since it was
saved), `predecessor_accepted` (the version this one revises was accepted
meanwhile), `lead_not_open`, `status_changed`.

### Discount approval: `POST /quotations/{id}/request-approval`

A draft whose discount is above its owner's limit is sent only once a manager
approves it. The draft carries what the builder needs:

```jsonc
"discount": {
  "effective_pct": "12.00",      // what the customer saves off the list price, all three tiers
  "owner_limit_pct": "5.00",     // null: no limit
  "approval_required": true,
  "send_gate": "required"        // what Send will do, below
},
"approval": {                    // the latest request, or null
  "request_id": "…", "status": "pending",
  "steps": [{"id": "…", "seq": 1, "role": "state_manager", "decision": null, "by": null,
             "remark": null, "decided_at": null, "decided_role": null}]
}
```

`discount` is on a draft only; null once sent.

| `send_gate` | The builder shows |
|---|---|
| `none_needed` | **Send** |
| `approved` | **Send**, and "Discount approved" |
| `required` | **Request approval** in place of Send |
| `pending` | "Waiting for approval" and the approver's role; Send disabled |
| `void` | "Approval no longer applies: the figures changed", and **Request approval** |
| `returned` | "Approval refused" with the remark (staff), and **Request approval** after an edit |

`POST /quotations/{id}/request-approval` with `{"remark": "…"}` (optional) returns
the quotation with `approval` pending. Errors: `approval_not_required` (just send),
`approval_pending`, `quotation_not_draft`, `no_approver` (nobody's limit covers the
discount: lower it).

- **Any save or delete of the draft cancels a pending request.** The approval is
  always for the figures the approver saw. Warn before saving while pending.
- The draft stays `draft` throughout. Approval changes what Send may do, not the
  status.
- The approver sees it in `GET /approvals/pending` as a row with
  `doc_type: "quotation"`, `document.number: null` (drafts have none),
  `document.party_name`, `document.total` and **`document.discount_pct`**. The
  decision (`POST /approvals/steps/{id}/decision`) returns the **quotation** for
  such a row, and can answer `409 figures_changed`. Its body is `DecisionResult`:
  read `data.doc_type` (`sales_order` or `quotation`), which every order and
  quotation now carries, to tell which came back.
- A dealer never sees `discount` (null) or who approved and why, on the detail or
  on either timeline.
- Staff read why it was asked in `approval.request_remark`, and on the timeline's
  `quotation.approval_requested` event.
- One step: the lowest manager above the owner whose limit covers the discount.
  The limits are stand-ins until the client confirms them: officer 5 %, District
  10 %, State 15 %, Regional 20 %, Admin-Sales no limit. Admins change them with
  `PUT /approvals/thresholds` and `doc_type: "quotation"`; rows carry `unit: "pct"`.

A quotation on stand-in prices **can** be sent; its PDF carries an "INDICATIVE
PRICING" banner and `is_provisional` is true. Show the same banner.

### `POST /quotations/{id}/transition`

```jsonc
{ "to": "accepted",                // accepted | rejected | negotiation
  "remark": "Confirmed on the phone, wants delivery next week",
  "expected_status": "viewed" }
```

Errors: `invalid_transition`, `quotation_expired` (past `valid_until`, even
before the nightly job has run), `quotation_superseded`, `lead_not_open`,
`status_changed`. Acceptance moves the lead to `won` and the response carries
`lead.stage`.

### `POST /quotations/{id}/revise`

```jsonc
{ "price_effective_date": null,    // defaults to today: a revision is a new offer at today's rates
  "expected_status": "rejected" }
```

`201` with a new draft: version n+1, the same number, `supersedes: { id, version }`,
lines copied and re-priced, `warnings` naming any line whose rate or slab changed
(`repriced`). `409 revision_exists` if an open draft of this number already
exists (open that one instead). Not from `draft` (edit it) or `accepted`, and
`409 quotation_superseded` on an older version: revise the current one.

### `GET /quotations/{id}/versions`

Every version of the number, oldest first, list-row shape. Any version's id works.

### `GET /quotations/{id}/timeline`

The quotation's events, newest first, keyset-paged, the lead timeline's shape:
`quotation.created`, `.updated`, `.lines_replaced`, `.sent`, `.viewed`,
`.accepted`, `.rejected`, `.negotiation`, `.expired`, `.revised`, `.deleted`.
Payloads carry `from`, `to`, `remark`, `actor_name`; `viewed` carries the open
count. The same rows also appear on `GET /leads/{id}/timeline`.

### `GET /quotations/{id}/pdf`

```jsonc
// 200
{ "data": { "url": "https://.../v1.pdf?...", "expires_at": "...", "filename": "QT-GJ-2026-27-00001-v1.pdf" } }
```

A URL valid for ten minutes. **Open it in a new tab; do not fetch it with the
bearer token.** `404` on a draft; `409 pdf_pending` while the worker has not
finished; `409 pdf_failed` with `pdf_error` when it gave up.

### `DELETE /quotations/{id}`

Body `{ "expected_status": "draft" }`. Drafts only, for roles holding
`quotations.delete`. `409 quotation_not_draft` otherwise. A sent document is
never deleted.

---

### `POST /pricing/quote-lines` - the preview, extended

The preview you already call learns the cascade, additively: each line accepts
optional `discount2_pct` and `discount3_pct` (default `"0.000"`), and each
returned line gains `discount1_amt`, `after_discount1`, `discount2_amt`,
`after_discount2`, `discount3_amt`, in the same positions as the quotation line
above. A caller sending one tier sees no change.

---

## 5. The public page: `/q/{token}`

This is a **public route on your app**, no sign-in. The share link the farmer
receives is `<your origin>/q/<token>`; the backend is told your origin so the
link points at your app. The page calls two endpoints, both without any
`Authorization` header:

### `GET /public/q/{token}`

```jsonc
{ "data": { "quote_no": "QT/GJ/2026-27/00001", "version": 1, "status": "viewed",
            "sales_type": "commercial", "seller": { "legal_name": "...", "gstin": "..." },
            "sent_at": "...", "valid_until": "2026-11-06", "expired": false, "superseded": false,
            "totals": { ... }, "line_count": 7, "pdf_ready": true,
            "pdf_url": "/public/q/{token}/pdf" } }
// 404 not_found for an unknown token
```

No party name, no mobile, no address, no lines: a link forwarded to the wrong
person learns a number and a total, nothing else. Show the number, the seller,
the validity, the total, and a **View quotation** button. If `expired` or
`superseded`, say so; the button still works. If `pdf_ready` is false, say
"preparing" and retry in a few seconds.

### `GET /public/q/{token}/pdf`

Redirects (`302`) to the PDF. **Open it in a new tab from the button, never on
page load.** This request is what records the view on the officer's side:
messengers fetch a link's landing page to draw a preview the moment the message
is sent, and a view recorded by a crawler would be worse than none. The
farmer's tap is the view.

Rate-limited to 60 a minute per link.

---

## 6. Screens

| Screen | Shows | Actions | Notes |
|---|---|---|---|
| **Lead detail, Quotations tab** | `GET /quotations?lead_id=` as cards: number or "Draft", version, status chip, total, sent and viewed dates, `pdf_state` | **New quotation**, enabled only when the lead is `qualified`, `quoted`, `negotiation` or `won`; on `new`/`contacted` show why; on `lost` say to reopen first | rows from a merged-in lead appear too, read-only; a `superseded_by` row renders muted |
| **Quotation builder** | header (party, partner, place of supply, price date, seller registration), the line grid with the product picker, three discount columns per line, live totals from `POST /pricing/quote-lines` on every change, and **the effective discount against the owner's limit** (`discount`) | **Save draft** (`POST` / `PUT lines`), **Send**, or **Request approval** by `discount.send_gate` | on `rate_changed`, show the changed lines, re-preview, let the user save again. Money comes back as strings; never compute a total on the screen |
| **Quotation detail** | the document as returned: status chip, the cascade columns, tax, totals, validity, `warnings`, the timeline, the versions strip, the share link with a copy button, **Open PDF** | **Send** (draft), **Accepted** / **Rejected** / **Negotiation** with a remark, **Revise**, **Delete** (draft, with the permission) | states: `draft`, `sent`, `viewed`, `negotiation`, `accepted`, `rejected`, `expired`, the `superseded_by` overlay on any of them, and `pdf_state` (`pending`: "preparing", poll; `failed`: show `pdf_error`). `is_provisional` shows the banner. `lead` may be null: show "lead not visible" |
| **Quotation list** | `GET /quotations`, keyset-paged, `include_total` for the count | filters: status, sales type, owner, partner, date range, search | `current_only` on by default; a toggle shows every version |
| **Public page `/q/{token}`** | number, seller, validity, total, `pdf_ready`, expired / superseded | **View quotation** opens `pdf_url` in a new tab | the button is the view. Never fetch the PDF on page load |
| **Approvals inbox** | quotation rows beside order rows, labelled "Quotation discount", with `discount_pct` | Approve / Reject with a remark | the decision returns the quotation |
| **Approval limits (admin)** | the quotation rows of `GET /approvals/thresholds` (`unit: pct`) beside the order rows | edit per role | a higher role's limit stays above a lower one's |
| **Partner portal** | list and detail, read-only | none | partner roles hold `quotations.view` only; the approval shows roles and outcomes, never names or remarks |

The lead list's `stage` chips gain `quoted`, `negotiation` and `won` as reachable
values.

---

## 7. Things that will look like bugs and are not

- **A draft has no number.** `quote_no` is null until sent. Sort drafts by `created_at`.
- **`share_url` is null on a draft** and present on every read once sent. It is recomputed by the server; it is not a field you store.
- **`pdf_state: pending` right after send** is normal for a few seconds. The message to the farmer waits for it.
- **`409 rate_changed` on send** even though the user changed nothing: a price list or tax rate was published under the draft. Re-preview; the new figures are the answer.
- **The view is recorded on the PDF open, not on the page load.** If your public page fetches the PDF automatically, every WhatsApp link preview will count as a view. Do not.
- **`expected_status` mismatches** (`409 status_changed`) mean another user moved the quotation. Reload and show the current state.
- **A second quotation can be accepted on a lead that is already `won`.** The quotation is accepted; the lead does not move again.
- **A subsidised enquiry** cannot get a `subsidised` quotation yet; the officer may choose `commercial` explicitly in the meantime, and the API refuses `subsidised`, `export`, `marketing` and `sample` with a message naming why.
