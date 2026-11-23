---
date: 2026-10-17
type: feature
title: "Dealer commission and TOD: stage 18 on the application, Accounts'
  approvals and payments, and the rates"
dataIds:
  - SUBS-016
  - SUBS-017
  - SUBS-018
author: Nakul Srivastava
breaking: false
---

## Before

The backend runs subsidy stage 18 (FS-033; handover `dealer-commission-contract.md`):

- once every payment is in, the co-ordinator records the dealer's commission and TOD;
- Accounts then approves it, returns it or cancels it, and pays it;
- the admin keeps the rates.

None of these 11 endpoints had a screen, so the dealer's commission could only be worked out by hand.

## Now

- **On a fully paid subsidy application: a Dealer commission card (SUBS-016).**
  - **Not recorded yet:** a co-ordinator (`subsidy.edit`) enters the GI fittings and the PVC and HDPE fittings. The installation comes from the calculation unless typed, and the TOD base is the commission base unless typed.
  - **Worked out as you type:**
    - cost before GST, less the fittings and installation, gives the commission base;
    - the commission and TOD at the rate in force on the full-FP date;
    - the total to the dealer.
  - **Checks before sending:** amounts that aren't rupees, and fittings and installation above the cost. Each is named on its field.
  - **Recorded:**
    - the server's figures, with To approve, To pay, Returned or Paid;
    - who recorded it, approved it and paid it, with the reference;
    - a return's remark.
    - **Record it again** while it waits or after a return.
  - **No rate in force:** the card says so. An admin gets a link to add one; anyone else is told who to ask.
  - **No dealer on the application:** the card says no commission is due.
- **Operations → Dealer commissions (SUBS-017),** for Accounts (`payments`):
  - To approve, To pay, Returned, Paid and All, in the URL, with Download Excel;
  - **Approve:** not on one you recorded (`own_decision`);
  - **Return** and **Cancel it:** each with a remark;
  - **Record payment:** the date (not in the future) and the UTR or cheque number.
  - The same actions sit on the application's card.
- **Subsidy masters → Commission rates (SUBS-018):**
  - a scheme's rates, newest first, each In force, Scheduled or Superseded;
  - **Add a rate** (`masters.edit`): system, partner type or one partner, commission %, TOD % and the start date;
  - a 0% rate retires its scope, and a clash on the same scope and day is refused.
- Walked through in the mock:
  - Admin on a desktop in light mode: recording, an error, the rates;
  - the Account Manager on a phone in dark mode and on a desktop: approving and paying.
  - axe found nothing.

## Discussion

- **The working mirrors the backend's own check** (migration 037: base = cost − fittings − installation; each amount to the paisa; total = both). It's shown while typing, but the server's figures are the ones kept and shown after.
- **Who sees which action** follows the router:
  - `payments.approve` approves and returns;
  - `payments.edit` pays;
  - `subsidy.view` cancels before approval, and Accounts cancels after;
  - `subsidy.edit` records.
- **Dealers don't see commissions yet (GAP-330),** so this is staff only.
- **The menu item** uses `payments`, the Accounts module. Co-ordinators work from the application.
- **Mock caveat:** every mock staff role signs in as the same user. The commission mock therefore puts the role into the recorder's id, so Accounts isn't taken for the recorder of what Admin recorded. The seeded commission is recorded by a co-ordinator, so Admin and Accounts can both approve it.

## Files changed

- `src/features/commission/` (new):
  - the contract, calls, queries, mutations and labels;
  - `application-commission.tsx`, `commissions-list.tsx`, `commission-decisions.tsx`, `commission-rates-panel.tsx` and `commission-parts.tsx`;
  - the tests.
- `src/app/(app)/dealer-commissions/page.tsx` (new), and `src/components/layout/navigation.ts`: the page and its menu item.
- `src/features/subsidy/components/application-detail.tsx`: the card on the application.
- `src/features/subsidy/components/subsidy-masters.tsx`: the Commission rates tab.
- `src/mocks/data/commission.ts` (new), `src/mocks/handlers/commission.ts` (new), `src/mocks/db.ts` and `src/mocks/handlers/index.ts`: the 11 endpoints with the backend's rules, and seeded rates and one commission.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SUBS-016, SUBS-017 and SUBS-018.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md` and `Docs/screenshots/commission/`: records and screens.

## Tests

- `src/features/commission/components/commission.test.tsx`:
  - **The contract:**
    - the preview and the scheme-wide rate for a sub-dealer, and `not_closed`;
    - recording again, with the server's figures;
    - fittings above the cost, refused on the field;
    - a retired rate (`no_rate`);
    - approve, then pay;
    - `own_decision`, `remark_required`, a future payment date and `commission_exists`;
    - a field officer refused;
    - rates newest first, an added rate, `rate_exists`, and Accounts refused.
  - **The screens:**
    - recording again with the working, and a fitting problem on its field;
    - no rate in force, and nothing on an open application;
    - approving and paying, returning with a remark, and the empty queue;
    - the rates with the one in force, and adding one.
