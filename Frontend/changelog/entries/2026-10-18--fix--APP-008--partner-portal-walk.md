---
date: 2026-10-18
type: fix
title: The dealer portal walk
dataIds:
  - APP-008
author: Nakul Srivastava
breaking: false
---

## Before

Nobody had walked the app as a dealer, a distributor or a sub-dealer since the portal screens were built. In the mock, a partner user saw:

- every lead in the company (132), with the whole company's pipeline on the dashboard;
- every order;
- every complaint.

The backend scopes these to the user's dealership (`partner_subtree`), so the mock was showing far more than a dealer will ever see.

## Now

Item 38 of `plan-13oct-2026.md`: each partner role walked every screen in its menu, and every staff screen by its address.

**What the walk found and what changed**

- **The mock scopes a partner user to their own,** as the backend does:
  - leads (the list, the count in the menu, and one lead, which is a 404 outside it);
  - the dashboard's figures;
  - orders (the list and one order);
  - complaints (the list and one complaint).
  - `src/mocks/data/partner-scope.ts` holds the rule.
- **Each demo partner user starts with eight new or contacted leads.** None of them has a quotation, order or customer yet, so no other seeded figure moves.
- **Headings** (axe `heading-order` and `page-has-heading-one`):
  - My ledger's "Your rating" is now a level-2 heading;
  - the empty Customers page's title is level 2;
  - the 404 page for an unknown address has its title as the page's level-1 heading.
  - `EmptyState` and `EmptyTitle` take `level={1}` for a state that is the whole page.

**What held**

- A partner's menu has ten items: Dashboard, Help, Leads, Customers, Sales orders, My ledger, Complaints, Marketing material, Schemes and Rewards.
- Each of 22 staff screens, opened by its address, says "You don't have access to this page". Among them are Quotations, Approvals, Users, Settings, Team map, Dispatch, Receipts and Products.
- No sideways scroll on a desktop or a 390 px touch phone. After the fixes, axe found nothing on any screen.

**Backend ask**

- **BE-030:** say on `GET /auth/me` whether tasks are on for dealers. While `tasks_for_dealers` is off, every page a partner user opens makes one refused `GET /tasks`, which the browser logs as an error.

## Discussion

- **The leak was the mock's, not the screens'.** Every screen shows what its endpoint returns. A dealer on staging will see their own rows, because the backend scopes them. The mock now behaves the same, so the next walk or demo shows what a dealer really sees.
- **Only new or contacted leads were handed over.** A first try that handed over leads with quotations and orders moved figures that ten other tests rely on: payments, schemes and the farmers' portal.
- **Tests that opened another dealership's record as a dealer** now hand that record to the dealer first. These were the dealer's view of a lead, the amend check, the reopen reason and points on a draft.
- **This is item 38, the last of the plan's numbered items.** The optional polish and the items waiting on others remain.

## Files changed

- `src/mocks/data/partner-scope.ts`: new, the partner scope and the demo partners' leads.
- `src/mocks/db.ts`: hands the leads over at reset.
- `src/mocks/handlers/leads.ts`, `dashboard.ts`, `orders.ts`, `complaints.ts`: scoped to the partner's own.
- `src/features/ratings/components/dealer-rating.tsx`, `src/features/payments/components/my-ledger.tsx`: the rating card's heading level.
- `src/features/customers/components/customers-search.tsx`: the empty state's level.
- `src/components/ui/empty.tsx`, `src/components/patterns/empty-state.tsx`, `src/app/not-found.tsx`: level 1.
- Tests given their own dealership's record: `lead-activity.test.tsx`, `orders-ui.test.tsx`, `complaints-reopen.test.tsx`, `rewards.test.tsx`, `payments.test.tsx`, `consolidate.test.tsx`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: APP-008.
- `docs/Backend-Tasks.md`: BE-030.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/partner-portal/*`.

## Tests

`src/mocks/handlers/partner-scope.test.ts`, 3 tests in `[APP-008] What a partner user reads in the mock`:

- each partner role reads only their dealership's leads, and the count agrees;
- another dealership's lead is a 404, and the dashboard sums the dealer's own;
- another dealership's order or complaint is a 404.

To check by hand in the mock, choose Preview as role → Dealer, then:

1. Open **Leads**: eight leads, all the dealership's.
2. Open `/users` by its address: "You don't have access to this page".
