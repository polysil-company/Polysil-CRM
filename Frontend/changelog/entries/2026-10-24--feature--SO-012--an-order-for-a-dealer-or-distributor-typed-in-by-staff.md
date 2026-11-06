---
date: 2026-10-24
type: feature
title: An order for a dealer or distributor, typed in by staff
dataIds:
  - SO-012
  - LEAD-008
author: Nakul Srivastava
breaking: false
---

## Before

Staff could only order for a dealer or distributor through a lead whose channel partner was that dealer, or from the dealer's accepted quotations (SO-011). A new order typed in directly had no way to name a dealer, so it was priced as a direct sale. The client said this blocked their staff from processing existing dealers' and distributors' orders (24 Oct).

## Now

**For a dealer or distributor**, on **New order** without a lead (commercial or industrial, staff only):

- **Search:** by name, code or contact person, among the dealers and distributors the user can see. It is the same search as the lead's **Assign** dialog.
- **Rates:** picking one sends `partner_id`, so the backend prices the order at that dealer's rates.
- **Details filled in:** the party's name, mobile, address and GSTIN, and the place of supply, come from the dealer's record. All stay editable.
- **If the dealer's record can't be loaded,** the field says so. The order still uses their rates; the details are typed in.
- **Not offered:**
  - on an order from a lead, which brings its own partner;
  - on export, sample or subsidised orders;
  - to a dealer's own users, who order for themselves.

**Backend asks** in `docs/Backend-Tasks.md`. Each says whether it can start before the client answers the questions in the document _Polysil CRM — Employees on dealers_ (24 Oct):

- **BE-039:** a quotation for a dealer, with no farmer's lead. Can start now.
- **BE-040:** the employee(s) on a dealer. The link can start now; what it grants waits.
- **BE-041:** a leaver's leads go to their dealer. Waits.

## Discussion

- **Frontend only.** The backend already takes `partner_id` from staff on a direct order (`services/orders.py`). It prices at that partner's tier and checks the partner is one the caller can see.
- **One search for dealers.** The lead's **Assign** dialog and this field share the search, moved to `choice-picker.tsx`. The dialog behaves as before (its tests pass unchanged).
- **The party is filled once, on picking.** Later edits stay. A slower answer for an earlier pick never overwrites a later one.
- **A campaign test given its own time budget.** It waits out the "Not saved" moment (a fixed few seconds) and types about 45 characters, which together sat at the 5 s default. It failed twice on a busy machine (#193 and this branch). It now has 15 s; its assertions are unchanged.
- **Commercial and industrial only.** These are the sale types a dealer buys under. A dealer's export or sample would be a new rule, so it is not offered.

## Files changed

- `src/features/orders/components/order-builder.tsx`: the dealer field, `partner_id`, and the party filled from the dealer.
- `src/features/leads/components/choice-picker.tsx`: new; the searchable picker and the partner search, moved from the Assign dialog.
- `src/features/leads/components/lead-assign-dialog.tsx`: uses them.
- `src/mocks/handlers/orders.ts`: a direct order takes a dealer staff picked, as the backend does.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SO-012.
- `docs/Backend-Tasks.md`: BE-039 to BE-041.
- `src/features/campaigns/components/campaigns.test.tsx`: an explicit 15 s budget for "adds a campaign, refusing a taken name".
- `Docs/Tested-Features.md`.

## Tests

- **New,** in `src/features/orders/components/order-builder.test.tsx`, `[SO-012] An order for a dealer or distributor, typed in by staff` (3 tests):
  - picking a dealer fills the party and place, and the saved order sends `partner_id` and has the dealer as its partner;
  - the field isn't on an order from a lead;
  - it isn't offered to a dealer's own users.
- **Unchanged and passing:** `lead-assign.test.tsx`.

To check by hand in the mock, as Admin:

1. Open **Sales orders → New order**.
2. Under **For a dealer or distributor**, type part of a dealer's name and pick it. The party and place fill in.
3. Add an item and save.
