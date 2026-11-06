---
date: 2026-11-05
type: feature
title: Distributor applications and the data sheet
dataIds:
  - CHNL-007
  - CHNL-008
author: Claude
breaking: false
---

## Before

- The backend's FS-071 (migration 078) turned dealer applications into **dealer and distributor** applications. It added Polysil's printed data sheet: telephone, when the firm was set up, the bank's name and branch, working capital, premises and vehicles, people, previous installations and the place of appointment.
- The company settings now name who decides each type, and which extra fields each type must have.
- The frontend knew only dealers and the firm, tax and bank fields:
  - none of the new fields could be seen or filled in;
  - a distributor couldn't be started;
  - Decide always offered a parent distributor, which a distributor application refuses.

## Now

- **Start an application** asks first whether it is for a new **Dealer** or **Distributor**. The type's deposit is fixed then (item 42 shows it).
- **The list** has a **Type** filter (`?type=` in the address), and each row says Dealer or Distributor.
- **An application's page:**
  - a Dealer or Distributor badge beside the status;
  - a **Data sheet** card with:
    - the business facts;
    - working capital, its rows with the backend's total;
    - premises and vehicles, with areas in the chosen unit;
    - people: the counts and each group, "3 × Plumbers · Drip laying · 4 years' experience";
    - installations done before. A part with nothing filled in says so in one line.
- **Edit details** (staff) and **the applicant's own page** share one form, so both gain the data sheet:
  - **Firm and tax:** telephone, established on (a date picker, from 1900 to today), and the place of appointment.
  - **Bank:** bank, branch and branch address, beside the account.
  - **Working capital:** one box per facility, up to 10, with its amount in lakhs; other sources; the saved total.
  - **Premises and vehicles:** areas in square feet or metres, office and godown area, two-wheelers, cars, other vehicles.
  - **People:** sales executives and technicians; groups of people, up to 20, each with a category, how many, qualification, type of work and experience.
  - **Installations done before:** up to 50, each with the year, customers, what was done, the scope and the cost in lakhs.
  - Each row has a remove button. A row left empty is dropped rather than refused, and a table at its limit says so.
  - The checks are the backend's own: lakhs and areas with at most two decimals, counts in range, years from 1950 to this year. A table's problem names its row ("Row 1: the amount in lakhs…"). A refusal for a row's field lands on its table.
- **Staff can change the type** in Edit details while the application is with the applicant or returned. The backend refuses it once a deposit is recorded, and the refusal shows.
- **Decide** on a distributor's application:
  - it says "A distributor sits directly under Polysil" and offers no distributor to pick;
  - the code example reads DIST-GJ-0003;
  - approving says "the distributor and its login are added".
- **"Still needed"** names the extra fields an administrator can require, such as Telephone, People (manpower) or Shop photo (document).
- **Wording:** the list and the toasts say "partner" or the type, not "dealer", where either is meant. A submitted application is decided by "the managers the company settings name", not "a State Manager or above".

## Discussion

- **Every new field is read leniently.** The test box doesn't run 078 yet, so an application without them must still open. A missing type is a dealer, which is all the backend made before 078. A missing data sheet is empty, in square feet.
- **The checks copy `api/schemas/dealer_applications.py`:**
  - `Lakhs` and `Area` patterns;
  - 10, 20 and 50 rows;
  - experience up to 80 years, people 1 to 9,999;
  - a year from 1950 to this year.
    The backend still checks everything.
- **Rows have no ids,** so a row's place is its key while typing. The tables are boxes, not a grid, because five inputs don't fit across a 360 px phone.
- **The total is the backend's** (`working_capital_total_lakhs`), shown "as saved". The form doesn't add rows up itself, to avoid a second rule.
- **The mock** now:
  - keeps the type and the data sheet;
  - checks the same rules;
  - works out the total;
  - asks for the extras the settings require;
  - lets the roles in `*_application_deciders` decide;
  - gives a distributor no parent and a `DIST-` code.
- **Not here:** the deposit (item 42) and the printed sheets (item 43).

## Files changed

- `src/features/dealer-applications/api/data-sheet.schemas.ts` — new: the data sheet's contract, read leniently, and its request shape.
- `src/features/dealer-applications/lib/data-sheet-draft.ts` — new: the form's draft, the backend's checks and the changed-fields body.
- `src/features/dealer-applications/components/data-sheet-editor.tsx` — new: the sheet's parts of the form, and the row tables.
- `src/features/dealer-applications/components/data-sheet-facts.tsx` — new: the sheet on an application's page.
- `src/features/dealer-applications/components/application-inputs.tsx` — new: the form's labelled inputs, moved out of `dealer-application-fields.tsx` so both files share them.
- `src/features/dealer-applications/api/dealer-applications.schemas.ts`, `dealer-apply.schemas.ts`, `dealer-applications.api.ts` — the type, the sheet, the list's type filter and staff's type change.
- `src/features/dealer-applications/components/dealer-application-fields.tsx`, `edit-dealer-application.tsx`, `dealer-apply-form.tsx` — the sheet in the shared form; row errors from the backend land on their table.
- `src/features/dealer-applications/components/start-dealer-application.tsx`, `dealer-applications-list.tsx`, `dealer-application-detail.tsx`, `dealer-application-actions.tsx`, `dealer-application-refusals.tsx` — the type when starting, the filter, the badge and card, and Decide for a distributor.
- `src/features/dealer-applications/lib/dealer-application-labels.ts` — the type, unit, scope and extra-field words.
- `src/mocks/handlers/dealer-applications.ts` — the type, the sheet with its checks and total, the required extras and the deciders from the settings, and a distributor's approval.
- `Docs/plan-13oct-2026.md`, `Docs/Tested-Features.md`, `Docs/screenshots/partners/` — records and screens.

## Tests

- `[CHNL-007] Distributor applications (FS-071), through the API`:
  - a distributor's application starts, and the list filters by type;
  - the data sheet saves with its tables and total, and an amount with three decimals is refused;
  - a required extra (Telephone) appears in "still needed" once the setting asks for it.
- `[CHNL-007] The data sheet and the type on the screens`:
  - starting a distributor's application from the list;
  - filling in a facility and a group of people, with "Row 1" named at fault first, then the sheet shown once saved;
  - approving a distributor with no distributor to pick, and the DIST- example.
- `[CHNL-007] The data sheet's checks and changes`:
  - an old backend reads as an empty sheet;
  - the backend's checks on dates, lakhs, areas, counts and years;
  - an empty row is dropped;
  - only changes are sent, and an emptied table as null.
- The existing application tests pass, with the row's name now including its type.
