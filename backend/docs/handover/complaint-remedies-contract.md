# Complaint Remedies Contract - after the QC verdict

> **Status: built.** The generated reference is `backend/docs/api/complaints.md` (the remedy) and `backend/docs/api/approvals.md` (refunds in the inbox). This page says what to build, and what the reference cannot show.

## What to build

1. **"Choose remedy"** on a `qc_approved` complaint, shown when `can.remedy`. Three options:
   - **Refund:** amount, payee name, optionally the dealer it is paid through, a remark.
   - **Replacement:** shows the defective lines that will be ordered free; a remark.
   - **No action:** a remark. Closes the complaint at once.
2. **The remedy panel** on the complaint: kind, status, and:
   - for a refund, its approval steps and, once paid, the payment reference;
   - for a replacement, a link to its order and the order's status.
3. **"Withdraw remedy"**, shown when `can.withdraw`, with a remark.
4. **The approvals inbox:** refund rows next to orders and discounts (`doc_type: "complaint"`). On the Account Manager's step, label the remark field **"Payment reference"**: it is required there.
5. **The approval limits screen (#35):** a third tab, **Refunds**, in rupees (`doc_type: "complaint"`). Say on the tab that the managers stack: a 50,000 refund needs District, then State.
6. **On a replacement order:** a link back to its complaint (`order.complaint`).

## The flow

```
qc_approved --QC chooses--> refund       -> remedy_pending -> managers by amount -> Accounts pays -> closed
                         -> replacement  -> remedy_pending -> Dispatch approves -> shipped       -> closed
                         -> no action    -> closed
remedy_pending --rejected / withdrawn / order cancelled--> qc_approved (choose again)
```

Two new statuses: `remedy_pending` and `closed`. A complaint closes itself; nobody closes it by hand. A closed complaint cannot be reopened yet.

## Choosing a remedy

`POST /complaints/{id}/remedy`, with `Idempotency-Key`:

```jsonc
{"kind": "refund", "amount": "12500.00", "payee_name": "Kiritbhai Shah",
 "paid_through_partner_id": "…", "remark": "Refund of the failed laterals"}
{"kind": "replacement", "remark": "Replace the failed laterals"}
{"kind": "none", "remark": "Installation fault, fixed on site"}
```

`amount` is a decimal string, above 0, two decimals at most. `amount`, `payee_name` and `paid_through_partner_id` belong to a refund only.

| Response | Meaning |
|---|---|
| `200` | the complaint, now `remedy_pending` or `closed` |
| `409 status_changed` | not `qc_approved`; reload |
| `403` | only QC chooses, and never the complaint's raiser or owner |
| `422` on a field | `amount`, `payee_name`, `paid_through_partner_id`, `remark` |
| `422 nothing_defective` | a replacement with no defective quantity |
| `422 replacement_unpriced` | a defective product has no price today, or its quantity breaks its unit; `fields` names the line |
| `422 no_approver` | nobody active holds a role the approval needs: tell the user to contact the admin |

`POST /complaints/{id}/remedy/withdraw` takes `{remark}`. A refund can be withdrawn while its approval is open. A replacement can be withdrawn until something has shipped; its order is cancelled. Otherwise it answers `409 status_changed`. `403` for anyone but QC (and for the complaint's raiser or owner); `422` on `remark`.

## Refund approval

Refund rows come through the existing approval endpoints:
- `GET /approvals/pending` lists them with `doc_type: "complaint"`. `document.number` is the complaint number, `party_name` the contact, `total` the refund amount.
- `POST /approvals/steps/{step_id}/decision` answers `DecisionResult` with `data.doc_type: "complaint"` and the complaint.
- The bell rings for each approver; there is no WhatsApp.

## The remedy shape

```jsonc
"remedy": {
  "id": "…", "kind": "refund", "status": "pending",   // pending | completed | rejected | withdrawn | cancelled
  "remark": "…",
  "refund": {"amount": "12500.00", "payee_name": "…", "paid_through": {"id": "…", "name": "…"},
             "approval": { /* the approval block, as on an order */ },
             "payment_reference": null},
  "replacement": null,                                 // or {"order": {"id", "order_no", "status"}}
  "chosen_by": {"id": "…", "full_name": "…"}, "chosen_at": "…", "completed_at": null
},
"closed_at": null
```

`remedy` is the live remedy, or the latest one. After a rejection it shows that rejected remedy until QC chooses again.

**A dealer** sees `kind`, `status`, `refund.amount`, the replacement order's number and status, and `closed_at`. `payee_name`, `paid_through`, `approval`, `payment_reference`, `chosen_by` and `remark` are null for a dealer.

## Who does what

| Role | Can |
|---|---|
| QC Manager | choose and withdraw a remedy |
| District, State, Regional Manager | approve a refund step, by amount |
| Account Manager | approve the payout (remark = payment reference); sees complaints, decides nothing on them |
| Dispatch Manager | approve and ship a replacement order |
| Raiser, owner, dealer | see the remedy; cannot choose it |

## Not decided yet

These are stand-ins; each may change once the client answers:
- who chooses the remedy;
- the refund limits;
- that a refund has no cap;
- who is paid, and how;
- who approves a free replacement;
- when a complaint counts as closed.
