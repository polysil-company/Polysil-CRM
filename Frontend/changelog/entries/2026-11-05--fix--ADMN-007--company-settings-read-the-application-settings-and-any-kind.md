---
date: 2026-11-05
type: fix
title: Company settings read the application settings and any kind added later
dataIds:
  - ADMN-007
author: Claude
breaking: false
---

## Before

- The backend's migration 078 (FS-071, dealer and distributor applications) seeds seven new settings:
  - the dealer's and the distributor's deposit;
  - who may lower or waive a deposit;
  - who decides a dealer application, and who decides a distributor one;
  - what each type of application must have before it is submitted.
- Five of them use two new kinds:
  - `set`: some of a list, none twice;
  - `staff_roles`: at least one staff role.
- The page read only `choice`, `int`, `roles`, `bands` and `slabs`. A single setting of any other kind broke the whole list, so once 078 is deployed, **Company settings** would show "We received data we couldn't read" instead of any setting.

## Now

- **The two new kinds:**
  - **`set`:** checkboxes of the backend's list, saved in the list's own order.
  - **`staff_roles`:** checkboxes of the staff roles, as for complaints. Saving none is refused on the card: "Choose at least one role."
- **A kind the page doesn't know yet** is shown read-only, as text, titled from its key. The rest of the page loads and saves as before, so a kind added later can't take the page down.
- **A new section, "Dealer and distributor applications"**, with titles for the seven settings:
  - "A new dealer's deposit, in rupees" and "A new distributor's deposit, in rupees";
  - "Who may lower or waive a deposit";
  - "Who decides a dealer application" and "Who decides a distributor application";
  - "What a dealer application must have" and "What a distributor application must have". Each choice is named in words: Telephone, Bank branch, Shop photo, "Sales executives and technicians"…
- **The mock** seeds the same seven settings, values and descriptions as 078. It checks a `set` against its list and `staff_roles` for at least one staff role, as the backend does.

## Discussion

- **Why read-only rather than an error for an unknown kind.** The first build chose the error state over guessing an editor. Showing the value as text still guesses nothing, and a missing editor for one setting costs far less than a blank page for all of them.
- **A set is saved in the backend's order,** whatever order the boxes were ticked in. Nothing here is a chain, so the order means nothing, and saving the same choice always sends the same list.
- **The deposits are `int` settings,** so they already worked. They only needed titles and a section.
- **Three tests broke with the calendar, not the code** (failing on `integration` too, from 4 Nov):
  - The holiday tests picked "a weekday three days ahead". From 4 Nov that is 9 Nov, a holiday the mock already has, so the add was refused as a repeat. The helper now also skips the seeded holidays.
  - The price-list test expected a list starting on 1 Nov to read "Published, starts later". It now expects "In force" once that day has passed.
- **Who may be ticked as a decider:** the staff roles from `GET /lookups/roles`, as for the other role settings. The backend refuses `system` and any partner role, and checks that the roles exist.

## Files changed

- `src/features/settings/api/settings.schemas.ts` — `set`, `staff_roles` and the read-only unknown kind; the value is read for each kind instead of matched against a union.
- `src/features/settings/components/company-settings.tsx` — the editors, checks and read-only text for the new kinds; the applications section and its titles.
- `src/features/settings/components/company-settings.test.tsx` — four new tests.
- `src/mocks/handlers/settings.ts` — the seven settings of migration 078 and their checks.
- `Docs/plan-13oct-2026.md` — Tier 5: every backend change from 23 Oct to 3 Nov the frontend still has to pick up, items 40 to 49; BE-023 to BE-025 ticked; BE-039 to BE-041 under Waiting.
- `Docs/Tested-Features.md`, `Docs/screenshots/settings/` — the story and its screens.
- `src/features/complaints/components/complaints-escalation.test.tsx`, `src/features/products/components/products-ui.test.tsx` — date-proof: no seeded holiday as "a day ahead", and the right phase for a list that has started.

## Tests

- `[ADMN-007] The application settings (FS-071)`:
  - the API checks a set against its list, and staff roles for at least one staff role;
  - the page ticks the required fields and the deciders under their own section, and saves the set in the list's order;
  - saving no role is refused on the card;
  - an unknown kind shows as text, while a number beside it still edits.
- The existing settings tests pass unchanged.
- Walked through in the mock as Admin, on a desktop in light mode and a phone in dark mode.
