---
date: 2026-10-18
type: feature
title: Warranty on orders and complaints, and warranty periods in Masters
dataIds:
  - SO-009
  - CMPL-011
  - MSTR-017
author: Nakul Srivastava
breaking: false
---

## Before

Nothing. Nobody could see whether goods sent on an order were still in warranty, a complaint said nothing about warranty, and there was nowhere to set how long a warranty lasts.

## Now

- **The order's Warranty card (SO-009).** On a shipped order, for those who see orders and dispatches, after the Payments card. Each line shows its status from its latest-ending dispatch: "In warranty until …", "Expired …", "No warranty", "No period on record" or "Not sent yet". Under it, each dispatch's period (from its DC date, or the day it left, for the months in force then) and the complaints raised on the product, in or out of warranty. A replacement order links the complaint it replaces. Skeleton while loading, `ErrorState` with retry on failure; hidden on a draft, from roles without dispatch view, and on a 403.
- **Warranty on complaint lines (CMPL-011).** Each product on a complaint shows In warranty or Out of warranty, until or ended when, and whether the period ran from the dispatch or from the supply date. Out of warranty blocks nothing.
- **Masters → Warranty periods (MSTR-017).** Everyone who sees Masters reads the default and each category's periods: in force, upcoming or ended, with their dates. Those who edit masters use **Set a period** to set one for the default or a listed category: 0 to 120 whole months, from tomorrow or later. The period in force ends the day before the new one starts. Today or earlier, and a second period on the same day (409 `term_exists`), are refused on the start-day field. Other field errors from the backend land on their fields, anything else in a toast.
- The mock answers all three endpoints. Its sample periods are 12 months by default and 24 for drip components, from 1 Apr 2026.

Walked in light and dark, on a desktop and a 390 px phone: axe found nothing, no console errors, no sideways scroll.

## Discussion

- A period never restates goods already sent, so a new one starts tomorrow at the earliest (`warranty.md`). The form starts on tomorrow and says why.
- The category picker offers the default and only the categories that already have a period. The backend has no category list yet (BE-024). `TODO(MSTR-017)` in `warranty-terms-panel.tsx` marks where every category goes once it does.
- The card is gated on `sales_orders.view` and `dispatch.view` together, as the endpoint is. Accounts (no dispatch view) doesn't see it.
- Quantities use the order line's unit and decimals ("7 NOS sent").

## Files changed

- `src/features/warranty/components/order-warranty.tsx`: new, the order's Warranty card.
- `src/features/warranty/components/warranty-chip.tsx`: new, the complaint line's warranty.
- `src/features/warranty/components/warranty-terms-panel.tsx`: new, the periods list, the Set a period form, and its rules (`termPhase`, `termProblems`, `requestOfTerm`).
- `src/features/warranty/api/*`, `src/features/warranty/lib/warranty-labels.ts`: the contract, calls, queries, mutation and labels.
- `src/features/orders/components/order-detail.tsx`: the card after Payments.
- `src/features/complaints/components/complaint-detail.tsx`: the chip under each product.
- `src/features/complaints/api/complaints.schemas.ts`: `warranty` on complaint lines.
- `src/features/masters/components/masters.tsx`: the Warranty periods tab.
- `src/mocks/data/warranty.ts`, `src/mocks/handlers/warranty.ts`, `src/mocks/db.ts`, `src/mocks/handlers/index.ts`, `src/mocks/handlers/complaints.ts`: the mock.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SO-009, CMPL-011, MSTR-017.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/warranty/`: records.

## Tests

- `src/features/warranty/components/warranty.test.tsx`, 15 tests:
  - `[SO-009] Order warranty (contract)`: periods from dispatches; 403 without dispatch view.
  - `[SO-009] OrderWarrantyCard`: shown on a shipped order; hidden from Accounts and on a 403.
  - `[CMPL-011] ComplaintWarranty`: in warranty from the dispatch, out of warranty from the supply date, nothing without an answer.
  - `[MSTR-017] Warranty periods (rules)` and `(contract)`: phases, months and start-day checks, closing the period in force, `validation_failed`, `term_exists` and `forbidden`.
  - `[MSTR-017] WarrantyTermsPanel`: lists and sets a period, a clash on the start day, read-only.
- By hand, in the mock:
  1. As Admin, open SO/GJ/2026-27/00001 and find the Warranty card.
  2. Open complaint Poly/Comp./2026-27/GJ/02 and find the chip on each product.
  3. Open Masters → Warranty periods and Set a period.
