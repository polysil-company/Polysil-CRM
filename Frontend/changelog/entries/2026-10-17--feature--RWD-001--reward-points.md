---
date: 2026-10-17
type: feature
title: "Reward points: balances, gifts and the gift desk, earning rules and
  point value, and points on a dealer's order"
dataIds:
  - RWD-001
  - RWD-002
  - RWD-003
  - RWD-004
author: Nakul Srivastava
breaking: false
---

## Before

The backend runs reward points (FS-032; handover `rewards-contract.md`, 19 endpoints):

- dealers and staff earn points by rules the admin sets;
- dealers spend them on a gift, or on an order.

None of it had a screen.

## Now

- **Channel → Rewards** (`/rewards`), for everyone holding `rewards`. The tab is in the URL.
- **Points (RWD-001):**
  - the balance, and what it is worth on an order at today's point value;
  - the history, newest first, each entry marked earned, taken back, spent or held, given back, expired or adjusted, with when points expire.
  - **Whose points:** a manager or Admin can look up a dealer's balance. A field officer sees only their own (`rewards` V:own).
- **Gifts (RWD-001):**
  - **The catalogue,** cheapest first.
  - **Ask for it:** a dealer asks for a gift its points cover, and the points are held at once. A gift it can't afford says how many more points are needed.
  - **Your requests:** with their state. A waiting request can be withdrawn, which gives the points back.
  - **Staff can't redeem yet (GAP-336).** The screen says so.
- **Gift desk (RWD-002, `rewards.approve`):**
  - the requests waiting, or all of them;
  - **Mark sent,** with an optional note;
  - **Refuse,** with a reason; the points go back.
- **Admin (RWD-003, `rewards.edit`):**
  - **Earning rules:** each in words, with its dates and how long its points last. Add a rule. A rule that has awarded points changes only its end date and the active switch (`rule_in_use`), and a taken code is refused on its field.
  - **Point value:** what a point is worth and the most of an order points may pay, from today, once a day (`settings_changed_today`).
  - **Gifts:** add, change, or switch one off.
  - **Adjust points:** a dealer's or your own balance, with a reason. It shows the new balance before saving.
- **Points on an order (RWD-004).** A dealer's draft order gets a Reward points card:
  - **The limit:** up to the order limit (10% of the total, GST included), with "Use N points" as a shortcut.
  - **Held at once:** the points are held as soon as they are put on, and can be taken off again.
  - **At submit:** the backend takes them off "To pay" as a benefit, which the order's Schemes card lists as "Reward points redeemed". Points not needed go back.
- Walked through in the mock:
  - a dealer on a phone in dark mode: points, gifts, asking, an order's points;
  - Admin on a desktop in light mode: the desk, a refusal, rules, a new rule, the point value, an adjustment.
  - axe found nothing.

## Discussion

- **A new permission module, `rewards`.** RBAC.md §6 gives:
  - field officers V:own;
  - managers V:org;
  - Admin everything;
  - partner users view and redeem (GAP-043).
- **A duplicate `targets` entry** in the module list is removed.
- **Who may redeem.** The screen offers Ask for it and Use points only to partner users holding `rewards.create`. The backend refuses staff below Admin (GAP-336), and Admin redeeming its own points has no use yet.
- **Points held on a draft** are read from `GET /rewards/gift-redemptions?kind=order&status=pending`. The order itself carries them only after submit.
- **Mock caveats:**
  - The demo dealer user's partner, Shah Agro Traders, isn't among the seeded channel partners. Staff therefore look up Ambika Krishi Kendra, which has a seeded history.
  - Every mock staff role shares one user, so "your own" points are the same for all staff.

## Files changed

- `src/features/rewards/` (new):
  - the contract, calls, queries, mutations and labels;
  - `rewards-page.tsx`, `points-panel.tsx`, `gifts-panel.tsx`, `gift-desk.tsx`, `rules-panel.tsx`, `reward-settings-panel.tsx`, `reward-dialogs.tsx` and `order-points.tsx`;
  - the tests.
- `src/app/(app)/rewards/page.tsx` (new), and `src/components/layout/navigation.ts`: the page and its menu item.
- `src/features/orders/components/order-detail.tsx`: the Reward points card on a dealer's draft.
- `src/lib/auth/permissions.ts`: the `rewards` module.
- `src/mocks/data/rewards.ts` (new), `src/mocks/handlers/rewards.ts` (new), `src/mocks/db.ts`, `src/mocks/data/permissions.ts`, `src/mocks/handlers/index.ts` and `src/mocks/handlers/orders.ts`:
  - the 19 endpoints with the backend's rules;
  - the `rewards` grants;
  - points applied at submit and released on cancel, return and amend.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: the RWD domain, RWD-001 to RWD-004.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md` and `Docs/screenshots/rewards/`: records and screens.

## Tests

- `src/features/rewards/components/rewards.test.tsx`:
  - **Points and gifts:**
    - balances by role, with a field officer's scope;
    - a gift held, refused when not covered, and withdrawn.
  - **The desk:** `remark_required`, a refusal giving the points back, and `redemption_closed`.
  - **Admin:** `rule_in_use`, an end date, `code_taken`, settings once a day, an adjustment, and a dealer refused.
  - **Points on an order:**
    - held, `points_on_order`, taken off, `over_redeem_limit`, `insufficient_points`, and staff refused;
    - taken off "To pay" at submit as a benefit.
  - **The screens:**
    - a dealer's points and asking for a gift;
    - a manager looking up a dealer;
    - refusing at the desk;
    - adding a rule;
    - changing the point value;
    - adjusting a balance;
    - using points on a draft and taking them off.
