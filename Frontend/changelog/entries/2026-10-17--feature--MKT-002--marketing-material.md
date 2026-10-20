---
date: 2026-10-17
type: feature
title: "Marketing material: order from the catalogue with both shares, approve
  and send, and keep the catalogue"
dataIds:
  - MKT-002
  - MKT-003
  - MKT-004
author: Nakul Srivastava
breaking: false
---

## Before

The backend runs marketing material ordering (FS-034; handover `marketing-material-contract.md`, 11 endpoints): a 17-item catalogue with today's price and the company's share, orders split between the company and the dealer, District Manager approval, and dispatch by the marketing team.

Channel → Marketing was a "Soon" item with no screen.

## Now

- **Channel → Marketing material** (`/marketing`), for everyone holding `marketing_material`. The tab, the list's view and the open order are in the URL.
- **Order material (MKT-003):**
  - the catalogue as cards: price per unit, "Indicative" on a stand-in price, and what the company pays;
  - **Add**, then a quantity stepper; the basket lists what is in it, with **Value**, **Company pays** and **Dealer pays** worked out live as the backend does;
  - **staff** pick the dealer it is for, or leave it empty for their office's own use, which the company pays in full; a **dealer** orders for itself;
  - **Place order** sends it straight to the District Manager (there is no draft) and opens it. An item taken off the catalogue meanwhile is refused with a message.
- **Orders (MKT-003):**
  - views by who you are: **Mine**; **To approve** (District Managers); **To send** (the marketing team); **All** (staff);
  - each row with its status, who it is for, the office, who asked, and both shares;
  - **Download Excel** with the same view.
- **An order (MKT-003, MKT-004)** opens in a dialog:
  - its lines with value and both shares, the totals, the remark, the decision and the dispatch;
  - the buttons come from the order's `can`: **Approve**, **Refuse** (a reason is required), **Cancel order** (a reason once approved), **Record dispatch** (a date not in the future, and a reference);
  - nobody approves their own order; someone acting first, or an order that isn't yours, says so;
  - a dealer never sees who decided or dispatched.
- **Catalogue (MKT-002, `marketing_material.edit`):**
  - every item, switched-off ones marked;
  - **Add an item** (code, name, unit, price, company share);
  - **Change** (a new price or share starts today; `price_changed_today` lands on the price);
  - **Switch off** or **Offer again**;
  - a taken code is refused on its field.
- Tables that scroll sideways on a phone take keyboard focus. The dealer ledger's table gets the same fix.
- Every list has its loading skeleton, empty state per view, and error with retry. Walked through in the mock, with axe finding nothing:
  - a dealer on a phone in dark mode: the catalogue, the basket, a placed order;
  - a District Manager on a desktop in light mode: to approve, the order, a refusal without a reason;
  - Admin: a dispatch, the catalogue, a change.

## Discussion

- **A new permission module, `marketing_material`,** as the backend checks it. Migration 038 seeds no role grants, so **BE-028** asks who gets what. Until then the mock follows the handover:
  - field staff and dealers order;
  - District and State Managers also approve;
  - Admin keeps the catalogue and dispatches.
- **The old "Marketing" item** (MKT-001, marketing offers, "Soon") is now Marketing material. MKT-001 stays planned in the registry.
- **The preview is only a preview.** The basket's shares are worked out in whole paise the way the backend does. The saved order's figures are the ones shown afterwards.
- Built to the backend's contract and checked against the mock only; not yet checked on staging.

## Files changed

- `src/features/marketing/api/` — schemas, API calls, queries and mutations for the catalogue and orders.
- `src/features/marketing/lib/marketing-labels.ts` — status labels and badges, view names, the share preview.
- `src/features/marketing/components/` — the page and its tabs, ordering, the orders list, the order dialog with its actions, the catalogue admin, and tests.
- `src/app/(app)/marketing/page.tsx` — the route.
- `src/components/layout/navigation.ts` — Marketing material in Channel.
- `src/lib/auth/permissions.ts` — the `marketing_material` module.
- `src/mocks/` — the catalogue, four seeded orders, all eleven endpoints, and the grants.
- `src/features/payments/components/partner-ledger.tsx` — the ledger table takes keyboard focus when it scrolls.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — MKT-002…004.
- `../docs/Backend-Tasks.md` — BE-028.

## Tests

- `src/features/marketing/components/marketing.test.tsx`: 12 tests.
  - contract: `[MKT-003] Marketing orders`, `[MKT-004] Deciding and sending`, `[MKT-002] The catalogue`;
  - screens: `[MKT-003] MarketingPage` (a dealer's order, approving, a refusal's reason, a dispatch and the catalogue).
- By hand:
  1. As a dealer, open Channel → Marketing material, add items and place the order.
  2. As a District Manager, approve or refuse it under To approve.
  3. As Admin, record the dispatch under To send, and change an item under Catalogue.
