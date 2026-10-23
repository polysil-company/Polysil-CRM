# Orders API Contract - `/api/v1/orders`, `/api/v1/approvals`, `/api/v1/dispatches`

> **Status: shipped.** The generated contract is `backend/docs/api/orders.md`, which
> is the record; this document is the context around it and matches it. Every error
> code below exists in the build. A partner user's order detail and timeline carry
> no internal remark and no approver name, as described under the portal view.
> Companions: `18-Quotations-API-Contract.md` (the accepted quotation an order is
> made from) · `17-Products-and-Pricing-Handover.md` (the product picker and the
> live preview) · `04-Permissions-RBAC.md` (who sees and approves what).

---

## What this is

An officer, a manager or a dealer turns one or more **accepted quotations**, or a
list typed straight in, into a **sales order**. Submitting it gives it a number and
sends it through an **approval chain** chosen by its value: District, then State,
then Regional Manager as the value rises, then Accounts, then Dispatch. Once
approved, Dispatch records what left the warehouse, line by line, as many times as
it takes; a balance that will never ship is **closed short**.

It is built in three parts, in this order: the approval engine, orders on it,
dispatch. The approval screens are generic: complaints and the quotation discount
approval will reuse them later.

---

## 1. Conventions

Everything in `13-Leads-API-Contract.md` §1 and `18-Quotations-API-Contract.md` §1
applies. In particular:

| | |
|---|---|
| Money and quantities | decimal **strings**: money two decimals, quantities three. Every figure the order prints is in the response; never compute a total on the screen |
| Idempotency | `Idempotency-Key` on every POST, PATCH, PUT and DELETE. **A refusal is stored against its key:** after a `409 rate_changed`, a `422` on a dispatch, or any refusal the user fixes and retries, send a **new** key |
| `expected_status` | send the status you rendered on submit and cancel; `409 status_changed` if it moved |
| Blocks you may not see | `lead`, `partner`, `owner` can be `null` and `quotations` can be `[]` when the caller cannot see them. The Dispatch Manager sees no lead, partner or quotation; Accounts sees no partner. Render "not visible to you", not an error. `party` and `delivery_address` are always present |

---

## 2. The order's life

```
draft ──submit──> submitted ──every step approves──> approved ──dispatch──> partially_dispatched ──> dispatched
  ^                    │                                 │                         │
  └──any step rejects──┘                                 └──close short──> closed_short <──┘
draft, submitted, approved (nothing shipped) ──cancel──> cancelled
voiding a dispatch moves dispatched or partially_dispatched back
```

- A rejected order goes back to **draft**, keeps its number, and shows
  `last_rejection` until it is submitted again. Submitting again re-runs the whole
  chain.
- After a dispatch, a void or a close, the status is worked out from the lines.
  Show `qty_dispatched`, `qty_short` and `qty_open` per line.
- An approved order cannot be edited; it can only be cancelled before anything ships.

### How the chain is chosen

Thresholds are set by an admin (stand-ins today: District up to 1,00,000, State up to
5,00,000, Regional above, all including GST). The chain is every manager level up to
the band, **minus levels at or below the order owner's own**, then Accounts, then
Dispatch. A District Manager's own small order goes straight to Accounts; a dealer's
starts at the District Manager.

---

## 3. Orders

### `POST /api/v1/orders` - create a draft

```json
{
  "order_type": "commercial",
  "quotation_ids": ["…"],
  "lead_id": null,
  "partner_id": "…",
  "party": {"name": "Rameshbhai Patel", "mobile": "+919876543210", "address": "Vadod, Anand", "gstin": null},
  "delivery_address": "Farm 12, Vadod",
  "place_of_supply_territory_id": "…",
  "seller_gstin_id": null,
  "price_effective_date": "2026-10-05",
  "payment_terms": "full_payment",
  "remarks": "Deliver before Diwali",
  "lines": []
}
```

**From quotations** (`quotation_ids`, `lines` empty):
- Only **accepted**, current quotations that are not already on another order.
- They must agree on partner, place of supply, seller registration, price date,
  office and territory. The order takes those from them; do not send different
  values (`422 quotations_disagree` names the field).
- **One lead:** the farmer is the party. **Several leads of one dealer:** a
  consolidated order; the dealer is the party and the order has no single lead.
- Lines are imported. Any line whose figures changed since the quotation (usually a
  GST rate that moved) is listed in `warnings` as `repriced`; show it before saving.

**Direct** (`lines`, no `quotation_ids`): lines as on a quotation (`product_id`,
`qty`, `discount_pct`, `discount2_pct`, `discount3_pct`, and the preview's
`price_list_item_id` and `gst_rate_id`). The price date is the user's choice. A lead,
if given, must be qualified or later.

**Types:** `commercial` and `industrial` only; the others answer
`422 order_type_unsupported`.

**Partner:** a dealer's own order needs no `partner_id` (it is theirs); sending `null`
from a dealer is `422 partner_required`.

**201** returns the order (below). It has **no number** until it is submitted.

### `GET /api/v1/orders` - the list

Newest first, keyset (`cursor`), like leads and quotations. Filters: `status`,
`order_type`, `partner_id`, `lead_id`, `owner` (`me` or a user id), `q` (number,
party name, mobile), `from`, `to` (dates, IST), `include_total`. Each row: the header
without lines, plus `dispatched_pct`, `is_provisional` and `approval_waiting_on` (the
role the order is waiting for).

### `GET /api/v1/orders/{id}` - the detail

```json
{
  "id": "…", "order_no": "SO/GJ/2026-27/00001", "status": "submitted", "order_type": "commercial",
  "party": {"name": "…", "mobile": "…", "address": "…", "gstin": null},
  "partner": {"id": "…", "name": "Shah Irrigation"}, "lead": {"id": "…", "inquiry_no": "…"},
  "quotations": [{"id": "…", "quote_no": "QT/GJ/2026-27/00007", "version": 2}],
  "owner": {"id": "…", "name": "…"}, "delivery_address": "…", "payment_terms": "full_payment",
  "seller": {"gstin": "…", "legal_name": "…", "state_code": "GJ"},
  "place_of_supply": {"state_code": "GJ"}, "intra_state": true,
  "price_effective_date": "2026-10-05", "tax_date": "2026-10-06", "is_provisional": false,
  "lines": [{
    "id": "…", "line_no": 1, "product_id": "…", "description": "…", "hsn_code": "3917", "uom": "MTR",
    "qty": "18.000", "rate": "103.19", "gross": "1857.42",
    "discount_pct": "10.000", "discount1_amt": "185.74", "after_discount1": "1671.68",
    "discount2_pct": "5.000", "discount2_amt": "83.58", "after_discount2": "1588.10",
    "discount3_pct": "0.000", "discount3_amt": "0.00",
    "taxable": "1588.10", "gst_slab": "5.000", "cgst": "39.70", "sgst": "39.70", "igst": "0.00", "total": "1667.50",
    "qty_dispatched": "0.000", "qty_short": "0.000", "qty_open": "18.000"
  }],
  "totals": {"gross": "…", "discount": "…", "taxable": "…", "cgst": "…", "sgst": "…", "igst": "…", "total": "…"},
  "approval": {
    "request_id": "…", "status": "pending",
    "steps": [
      {"id": "…", "seq": 1, "role": "district_manager", "decided_role": null, "decision": "approve",
       "by": {"id": "…", "name": "…"}, "remark": null, "decided_at": "…"},
      {"id": "…", "seq": 2, "role": "account_manager", "decided_role": null, "decision": null,
       "by": null, "remark": null, "decided_at": null}
    ]
  },
  "last_rejection": null,
  "dispatches": [],
  "warnings": [],
  "pdf_state": "none", "pdf_error": null, "confirmation": null,
  "submitted_at": null, "approved_at": null, "cancelled_at": null, "created_at": "…"
}
```

- `pdf_state`: `none` before approval, `pending` while the worker makes the PDF (a
  few seconds), `ready`, or `failed`. `pdf_error` says why it failed; it is null for a
  dealer.
- `confirmation`: whether the buyer got the WhatsApp confirmation on approval.
  `queued`, `no_mobile` (show "No mobile on the order: call the buyer"), or `disabled`
  (the message is switched off). Null before approval.

- `approval` is null until the first submit, then the latest chain. Draw it as a
  stepper. `decided_role` is set when a higher manager decided a step on behalf of an
  absent one ("State Manager, for the District step").
- **Dealers see less:** for a dealer, distributor or sub-dealer, `by` and `remark` are
  null on every step, and `last_rejection.remark` is a stock sentence. Internal notes
  never reach a dealer.

### `PATCH /api/v1/orders/{id}` · `PUT /api/v1/orders/{id}/lines`

Draft only (`409 order_not_draft`). Header fields, or all the lines at once. Every save
re-prices. On an order made from quotations the fields they fix stay fixed.

### `POST /api/v1/orders/{id}/submit`

`{"expected_status": "draft"}`. Re-prices at the order's price date with GST at
today's date, gives the order its number, and builds the chain. **200** returns the
order with `approval`.

| Refusal | Meaning |
|---|---|
| `409 rate_changed` | a price or tax moved; the new figures are in `fields`. Re-preview and submit with a new key |
| `422 no_lines`, `422 zero_total` | nothing to approve |
| `422 lead_not_open` | the lead was lost, merged or went dormant |
| `422 seller_registration_ended` | the seller GSTIN is no longer in force |
| `422 no_approver` | nobody holds a role the chain needs (Accounts or Dispatch); an admin must assign one |

### `POST /api/v1/orders/{id}/cancel`

`{"remark": "…", "expected_status": "…"}`, remark required. From draft or submitted by
the owner or creator, or by a State Manager or above; from approved (nothing shipped)
by a State Manager or above. `409 order_dispatched` once something has shipped;
`409 order_not_cancellable` otherwise.

### `DELETE /api/v1/orders/{id}`

A draft that was never submitted. A numbered draft is cancelled instead
(`409 order_was_submitted`).

### `GET /api/v1/orders/{id}/pdf`

`200 {url, expires_at, filename}`: a link valid for ten minutes. **Open it in a new
tab; do not fetch it with the bearer token.** Ask for it when the user clicks, not on
page load.

| Answer | Meaning |
|---|---|
| `404` | not approved yet, or not in your scope |
| `409 pdf_pending` | being made; poll the order until `pdf_state` is `ready` |
| `409 pdf_failed` | the worker gave up; staff see `fields.pdf_error` |
| `409 order_cancelled` | the order was cancelled; its PDF is withdrawn |
| `409 storage_unavailable` | file storage is down; try later |

The PDF prints the order number, the approval date, the seller, the buyer, delivery and
place of supply, every line with its discounts and tax, the totals and the payment
terms. It never prints approver names or remarks.

### `GET /api/v1/orders/{id}/timeline`

Newest first; no money in any event. Approval events show who and why for staff,
only the outcome for dealers.

---

## 4. Approvals

### `GET /api/v1/approvals/pending` - my queue

Steps waiting on me: my role, earlier steps done, documents I can see, never my own.
Oldest first. Each row: `step_id`, `seq`, `role`, `stalled`, `doc_type`, `document`
(id, number, party, total, `is_provisional`, raised by, raised at), `waiting_since`.

- A manager also sees a **stalled** lower step (nobody of that role covers the order)
  and may decide it.
- `?include_below=true` lists every lower step in the manager's area, so a State
  Manager can cover a District Manager on leave.
- Show the provisional badge before the remark box: stand-in prices.

### `POST /api/v1/approvals/steps/{step_id}/decision`

```json
{"decision": "approve", "remark": "Payment received against invoice 4411"}
```

- The remark is required to **reject**, and on **every Accounts decision** (Accounts
  checks payment outside the system; the remark is the record).
- **200** returns the chain and the order's new status.
- `403 not_your_step`, `403 self_approval`, `409 step_already_decided`,
  `409 earlier_step_undecided`, `409 request_closed` (cancelled meanwhile).

### `GET /api/v1/approvals/{request_id}`

The chain, as on the order.

### `GET · PUT /api/v1/approvals/thresholds` - admin

The ceilings per role (and per territory, optional). A change applies to orders
submitted afterwards; a waiting chain keeps its steps.

---

## 4a. WhatsApp messages about orders

Sent by the backend in the same step as the decision. The frontend sends nothing.

| When | To | Says |
|---|---|---|
| an approval step opens | each person who may decide it, except whoever submitted | "order SO/… for <party>, value Rs …, is waiting for your approval" |
| the last step approves | the buyer's mobile on the order | "your order SO/… is confirmed, value Rs …" |
| the order is approved or returned | the order's owner | "order SO/… for <party> has been approved / returned for changes" |

A person gets one waiting message per step per hour, so a resubmit loop does not
flood them. Each message can be switched off on the backend; the order's
`confirmation` field says what happened to the buyer's.

## 5. Dispatch

### `POST /api/v1/orders/{id}/dispatches`

For an approved or partly dispatched order.

```json
{
  "dc_no": "DC-2291", "dc_date": "2026-10-07",
  "invoice_no": "GJ/INV/0912", "invoice_date": "2026-10-07",
  "dispatched_at": "2026-10-07T16:30:00+05:30",
  "transporter": "Shree Logistics", "vehicle_no": "GJ03AB1234",
  "lines": [{"order_line_id": "…", "qty": "12.000"}]
}
```

- At least one line, each line once, quantity above zero, in the line's unit
  (a whole-number unit refuses `0.5`), and at most the line's open quantity.
- `dispatched_at` cannot be in the future.
- Warnings, not refusals: an invoice date before the DC date, an invoice number
  already used.
- The system **records** the invoice number from the accounts system; it does not
  issue invoices.
- **201** returns the dispatch (`D/<order number>/<n>`) and the order's new status.

### Other dispatch endpoints

| Endpoint | Does |
|---|---|
| `GET /api/v1/orders/{id}/dispatches` | the order's dispatches |
| `GET /api/v1/dispatches` | Dispatch's list across orders (`from`, `to`, `order_id`, `partner_id`) |
| `POST /api/v1/dispatches/{id}/void` | `{"remark": "…"}`; the dispatch stays on record, marked void; its quantities become open again |
| `POST /api/v1/orders/{id}/close-short` | `{"remark": "…"}`; from approved or partly dispatched; every open quantity becomes short and the order is closed |

---

## 6. Screens

| Screen | Who | Notes |
|---|---|---|
| Order list | everyone with orders | status chips, dispatched bar, "waiting on", provisional badge |
| New order | officer, manager, dealer | pick accepted quotations that agree, or type lines; price date only for a direct order; live figures from `POST /pricing/quote-lines`; show `repriced` warnings |
| Order detail | everyone | lines with sent / short / open, the chain as a stepper, the last rejection while in draft, dispatches, timeline; actions by status and permission; "Download PDF" when `pdf_state` is `ready`, "Preparing PDF" while `pending`; a "No mobile: call the buyer" note when `confirmation` is `no_mobile` |
| My approvals | every approver | the queue, a stalled badge, an "include lower steps" toggle for managers, approve or reject with remark |
| Dispatch entry | Dispatch Manager | open quantities pre-filled per line; DC and invoice fields; warnings shown, not blocking |
| Approval thresholds | admin | the bands per role and territory |

---

## 7. Not in this release

- Payments and the dealer ledger; stock and warehouses; credit limits.
- Export, sample, marketing material, subsidised and replacement orders.
- Schemes (the fourth discount).
- Changing an approved order.
