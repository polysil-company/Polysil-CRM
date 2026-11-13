---
date: 2026-10-17
type: feature
title: "Payments: on the order, record a payment, receipts for Accounts, and the
  dealer ledger and credit standing"
dataIds:
  - ACCT-002
  - ACCT-003
  - ACCT-004
  - ACCT-005
author: Nakul Srivastava
breaking: false
---

## Before

The backend records money received against sales orders (handover `payments-contract.md`, 8 endpoints): receipts, how each is spread over a dealer's orders, up to five planned instalments per order, the dealer ledger and the dealer's credit standing. Nothing is collected online; it is a record.

None of it had a screen. The Accounts queue (ACCT-001) only sent orders on to Approvals.

## Now

- **Payments on the order (ACCT-002, ACCT-004).** A submitted order gets a Payments card (hidden on a draft, and when the order carries no `payments` block):
  - **To pay, Received, Balance,** and a status badge: Nothing to pay, Unpaid, Part paid, Paid or Overpaid;
  - **instalments** with their due dates, and an overdue notice when one is past due and unpaid;
  - **receipts** that went on this order, with mode, reference and date;
  - **Record payment** (`payments.create`): opens on this order. A direct (farmer) order's payment goes on it in full;
  - **Plan instalments** (`payments.edit`): up to five rows, which must add up to what is left to pay.
- **Record a payment (ACCT-002):** dealer, mode, reference (required for NEFT, UPI and cheque), date received, amount, short-payment flag, remark, and an amount per open order of that dealer, with each order's balance and what stays on account shown live. The backend's refusals land on their fields: a reference already recorded for the dealer, more spread than received, a no-dealer payment not fully spread, an order that can't take a payment, an order of another dealer.
- **Operations → Receipts (ACCT-003, `/receipts`),** for staff who may view payments:
  - newest first, with a dealer filter and **Show voided**;
  - each receipt: who, mode and reference, when received and who entered it, the orders it went on (links), and what is still on account;
  - **Put the rest on orders:** spreads what is left of a dealer's receipt, never more;
  - **Void,** with a reason. It comes off every order it went on; it is entered again if it was wrong, never edited;
  - recording and voiding are hidden from readers (managers).
- **The dealer ledger (ACCT-005):** approved orders as debits, applied scheme and reward benefits and receipts as credits, with a running balance in words ("owed", "in credit", "Settled"), a date range with the balance brought forward, and what is on account but not on an order.
  - **Staff:** on a partner's page, under Credit standing.
  - **Partner users:** **My ledger** (`/ledger`) in their menu, for their own ledger.
- **Credit standing (ACCT-005),** staff only, on a partner's page: the credit limit (or "Not set: never checked"), the exposure (owed on open orders less payments), and what is available, with "Over the limit" when it goes negative. A 403 hides it.
- Every list and card has its loading skeleton, empty state and error with retry. Walked through in the mock: Accounts on a desktop in light mode (receipts, record, allocate, void, an order's payments), Admin on a partner's page (credit and ledger), a dealer on a phone in dark mode (My ledger). axe found nothing.

## Discussion

- **A new menu audience, `partner`.** "My ledger" is for partner users only; staff read a dealer's ledger from the partner page. The nav item's `audience` now takes `"partner"` beside `"staff"`.
- **Amounts in paise for sums.** What stays on account and the instalment totals are worked out in whole paise, so ₹0.10 + ₹0.20 never drifts.
- **The allocation editor offers at most ten payable orders,** newest first, each with its balance read from the order. A dealer with more open orders spreads the rest later from Receipts.
- **Not done here:** the payment status in the approvals inbox (`document.payment_status`) is left for a follow-up; the Accounts queue still sends orders to Approvals as before.
- Built to the backend's contract and checked against the mock only; not yet checked on staging.

## Files changed

- `src/features/payments/api/` — schemas, API calls, queries and mutations for receipts, allocation, void, instalments, ledger and credit.
- `src/features/payments/lib/payment-labels.ts` — mode and status labels, rupee checks, paise helpers.
- `src/features/payments/components/order-payments.tsx` — the order's Payments card and the instalment plan.
- `src/features/payments/components/record-payment-form.tsx`, `allocation-editor.tsx` — recording a payment and spreading it.
- `src/features/payments/components/receipts-list.tsx` — the Receipts page with void and allocate.
- `src/features/payments/components/partner-ledger.tsx`, `partner-credit.tsx`, `my-ledger.tsx` — the ledger and credit cards.
- `src/app/(app)/receipts/page.tsx`, `src/app/(app)/ledger/page.tsx` — the routes.
- `src/components/layout/navigation.ts` — Receipts (Operations) and My ledger (partners), and the `partner` audience.
- `src/features/orders/` — `payments` on the order, the `partner_id` list filter, the card on the order page.
- `src/features/partners/components/partner-detail.tsx` — credit standing and the ledger for staff.
- `src/mocks/` — seeded receipts and an instalment plan, and all eight endpoints.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — ACCT-002…005.

## Tests

- `src/features/payments/components/payments.test.tsx` — `[ACCT-002] Record a payment (contract)`, `[ACCT-003] Receipts: void and allocate (contract)`, `[ACCT-005] Ledger and credit (contract)`, `[ACCT-003] ReceiptsList`, `[ACCT-002] OrderPaymentsCard on the order`, `[ACCT-005] Ledger and credit cards`: 15 tests.
- By hand: switch the mock to Accounts, open Operations → Receipts, record, spread and void a payment; open the order from a receipt; open a dealer under Channel partners; switch to a dealer and open My ledger.
