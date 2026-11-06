---
date: 2026-11-05
type: feature
title: The deposit on dealer and distributor applications
dataIds:
  - CHNL-007
author: Claude
breaking: false
---

## Before

- FS-071 (migration 078) added a deposit step to dealer and distributor applications:
  - Each type's deposit is a company setting, copied onto an application when it starts.
  - It is recorded with a pay slip, or lowered or waived by the roles a setting names.
  - **An application can't be approved while it is unpaid** (`409 deposit_pending`).
- The frontend showed none of it. A manager pressing Approve on an unpaid application got a generic refusal, and nobody could record the deposit or waive it.

## Now

- **A Deposit card** on an application's page, when the backend sends one:
  - the status: Deposit due, Deposit paid, Deposit waived or No deposit;
  - the amount set for the type, the amount due now, and what was paid, when, and its reference;
  - every payment and relaxation in order, with who and why ("Due lowered from ₹50,000 to ₹0 · Ravi Joshi · Took over a business").
- **Record the deposit** (for staff the backend allows, while something is due):
  - the amount, filled in with what is due;
  - the day it was paid (a date picker, not after today);
  - a reference (UTR, cheque or receipt number);
  - the **pay slip**, uploaded first as a "Deposit pay slip" document, then named by the record;
  - a slip uploaded on a failed try is reused, not uploaded twice;
  - less than what is due, no slip, or a date after today are each named on their field.
- **Lower or waive it** (only the roles in `deposit_relaxation_roles`, never whoever started the application, and not after a payment): the new amount due, where 0 waives it, and why. The button reads "Waive it" for 0.
- **A submitted, unpaid application** says "Approval waits for the deposit". The list marks it **Deposit due**.
- **The deposit's refusals in words:**
  - **`deposit_pending`:** record it, or have it lowered or waived, before approving.
  - **`deposit_slip_missing`:** the recorded payment's slip was removed.
  - **`deposit_not_due` and `deposit_paid`:** the page refreshes to show where the deposit stands.
  - **`deposit_recorded`:** the type can't change any more.
  - **`not_your_relaxation`:** only the roles the settings name lower a deposit.
- **A refused decision** (a 403) now says it comes from the company settings, not "a State Manager or above".
- **Documents:** a dealer application offers a "Deposit pay slip" type, as the backend does.

## Discussion

- **Uploading the slip inside the dialog.** The backend wants the slip as a document first, then its id on the record. Asking staff to upload it under Documents and come back would be two steps for one job. The dialog does both, in order. If the record is then refused, the slip stays on the application's documents (where the backend keeps it) and is reused on the next try.
- **The amount starts at what is due.** The backend refuses less than due, and more than the amount set.
- **Who sees the buttons** comes only from the backend's `can.record_deposit` and `can.relax_deposit`. A backend before 078 sends neither, and no deposit, so the card doesn't show.
- **The mock:**
  - copies each type's deposit from its setting (0 by default, as the backend seeds);
  - the first seeded draft owes ₹50,000, so the card can be seen;
  - checks the slip, the amount and the date as the backend does;
  - works out paid, waived, pending or not required as `dealer_application_deposit_status()` does;
  - refuses approval while unpaid, and refuses a type change after a deposit entry.
- **India's date.** The mock now uses India's date for "not after today", here and for "established on" (item 41). After midnight in India, a check against UTC refused today.

## Files changed

- `src/features/dealer-applications/api/dealer-applications.schemas.ts`, `.api.ts`, `.mutations.ts`: the deposit, the list's deposit status, the two `can` flags, and the record and relaxation calls.
- `src/features/dealer-applications/components/deposit-card.tsx` (new): the card and its two dialogs.
- `src/features/dealer-applications/components/dealer-application-detail.tsx`, `dealer-applications-list.tsx`, `dealer-application-refusals.tsx`: the card, the notice, the list's badge, and the refusals.
- `src/features/dealer-applications/lib/dealer-application-labels.ts`: the deposit's words.
- `src/mocks/handlers/dealer-applications.ts`, `src/mocks/data/documents.ts`: the deposit and the pay-slip type.
- `src/features/documents/api/documents.test.ts`: a dealer application's types include the pay slip.
- `Docs/plan-13oct-2026.md`, `Docs/Tested-Features.md`, `Docs/screenshots/partners/`: records and screens.

## Tests

- **`[CHNL-007] The deposit (FS-071), through the API`:**
  - due and listed as such;
  - refused without a slip, refused below what is due, then recorded as paid;
  - only a named role lowers it, never higher, then waived;
  - approval refused with `deposit_pending`.
- **`[CHNL-007] The deposit on an application's page`:**
  - recording it with a pay slip (refused first without one), and the history after;
  - waiving it as a Regional Manager, refused first without a reason.
- The application, document and lead tests pass (216).
