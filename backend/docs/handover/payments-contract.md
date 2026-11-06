# Payments: receipts, instalments, the order's payments tab, the dealer ledger

> **Status: built on the backend.** These shapes are what the API returns. They only gain fields from here.

Accounts records money received against sales orders. A receipt can pay several orders, or part of it can stay on the dealer's account. Each order can have up to five planned instalments. Nothing is collected online; this is a record.

All paths are under `/api/v1`. Money is a decimal string with at most two places. A third decimal is refused (422). Every POST and PUT takes `Idempotency-Key`; never retry a 4xx under the same key.

## Who can do what

| Role | Sees | Records, allocates, voids, plans |
|---|---|---|
| Accounts, admin, MD | every receipt | yes |
| District, state, regional manager | receipts of dealers in their area, and of their orders | no |
| Field officer | nothing: `payments` on an order is `null` | no |
| Dealer | its own receipts and ledger, without remarks | no |

## The order: a new `payments` field on `GET /orders/{id}`

```json
"payments": {
  "payable": "118000.00", "received": "100000.00", "balance": "18000.00",
  "status": "part_paid",
  "overdue": true, "overdue_amount": "18000.00",
  "schedule": [ { "seq": 1, "due_on": "2026-10-10", "amount": "50000.00", "note": "Advance", "covered": true } ],
  "receipts": [ { "payment_id": "uuid", "received_on": "2026-10-03", "mode": "neft", "ref_no": "UTR…",
                  "amount": "100000.00", "is_short_payment": false } ] }
```

- `payable` is the order total less its applied scheme and reward benefits, the same figure as the order's top-level `payable` (schemes contract, handover 41).
- `status`: `not_applicable` (a zero-value or cancelled order), `unpaid`, `part_paid`, `paid`, `overpaid`.
- `null` when the user may not see payments: hide the tab.
- `covered`: received has reached this instalment, taken in due order.

The approvals inbox: `GET /approvals/pending` rows for orders gain `document.payment_status` (the same values). Show it beside the Accounts step.

## Record a payment: `POST /payments`

```json
{ "partner_id": "uuid", "mode": "neft", "ref_no": "UTR 4411 0098", "received_on": "2026-10-03",
  "amount": "125000.00", "is_short_payment": false, "remark": "Against invoices 4411 and 4412",
  "allocations": [ { "sales_order_id": "uuid", "amount": "100000.00" } ] }
```

Answer `201`:

```json
{ "data": { "id": "uuid", "partner": { "id": "uuid", "name": "Shah Irrigation" }, "mode": "neft",
            "ref_no": "UTR 4411 0098", "received_on": "2026-10-03", "amount": "125000.00",
            "allocated": "100000.00", "unallocated": "25000.00", "is_short_payment": false,
            "remark": "…", "entered_by": { "id": "uuid", "full_name": "…" }, "entered_at": "…",
            "voided": null,
            "allocations": [ { "sales_order": { "id": "uuid", "order_no": "SO/GJ/2026-27/00004" },
                               "amount": "100000.00", "order_balance": "18000.00" } ] } }
```

- `mode`: `neft`, `upi`, `cheque`, `cash`, `adjustment`. `ref_no` is required for the first three.
- No dealer (`partner_id: null`) means a direct farmer order's payment: allocate all of it.
- The screen: a dealer picker, then that dealer's open orders with balances (`GET /orders?partner_id=…`), and an amount per order. Show "unallocated" live.

| Code | Meaning |
|---|---|
| `422 ref_required` | NEFT, UPI or cheque without a reference |
| `422 over_allocated` | the amounts add up to more than the receipt |
| `422 must_allocate` | a no-dealer receipt not fully allocated |
| `422 partner_mismatch` | an order belongs to another dealer |
| `409 order_not_payable` | a draft, cancelled or zero-value order |
| `409 duplicate_reference` | this reference is already recorded for the dealer |

## Later actions

- `POST /payments/{id}/allocations` with `{ "allocations": [...] }`: spread what is left.
- `POST /payments/{id}/void` with `{ "reason": "…" }`: a mistake is voided and re-entered, never edited. `409 already_void`.
- `GET /payments?partner_id=&sales_order_id=&include_voided=&limit=&cursor=` and `GET /payments/{id}`.

## Instalments: `PUT /orders/{id}/payment-schedule`

```json
{ "instalments": [ { "due_on": "2026-10-10", "amount": "50000.00", "note": "Advance" },
                   { "due_on": "2026-11-10", "amount": "68000.00" } ] }
```

Replaces the plan (0 to 5 rows). Answers the order's `payments` block. `422 schedule_over_payable`; `409 order_not_payable`.

## Dealer ledger: `GET /partners/{id}/ledger?from=&to=`

```json
{ "data": { "partner": { "id": "uuid", "name": "Shah Irrigation" }, "from": "2026-10-01", "to": null,
            "opening_balance": "0.00",
            "rows": [ { "on": "2026-10-01", "kind": "order", "ref": "SO/GJ/2026-27/00004", "debit": "118000.00", "credit": null, "balance": "118000.00" },
                      { "on": "2026-10-03", "kind": "receipt", "ref": "NEFT UTR 4411 0098", "debit": null, "credit": "125000.00", "balance": "-7000.00" } ],
            "closing_balance": "-7000.00", "unallocated": "7000.00" } }
```

- Positive balance: the dealer owes. Negative: the dealer is in credit.
- An order counts on its approval date, at its total. A cancelled order never counts.
- `kind: "benefit"`: each applied scheme or reward benefit on those orders is a credit on the day it was applied; `ref` reads "Scheme SO/…" or "Reward points SO/…". So the balance is what the dealer owes after benefits.
- Also on the dealer portal, without remarks.

## Screens

| Screen | Notes |
|---|---|
| Order detail, Payments tab | the block above; Record payment and Edit instalments for Accounts |
| Record payment | dealer, mode, reference, date, amount, short flag, remark, per-order amounts |
| Receipts list (Accounts) | filters: dealer, order, voided; void; allocate the rest |
| Dealer ledger | date range, running balance; dealer portal too |
| Approvals inbox | `payment_status` beside the Accounts step |

## Defaults the client has not confirmed

- A dealer owes an order from its approval, at the order total, even if it is closed short.
- The short-payment flag is recorded and shown; it changes no figure.
- A debit to a dealer cannot be recorded yet.
