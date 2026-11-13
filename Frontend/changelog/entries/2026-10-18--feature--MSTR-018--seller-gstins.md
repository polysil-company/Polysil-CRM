---
date: 2026-10-18
type: feature
title: Seller GSTINs and their LUTs
dataIds:
  - MSTR-018
author: Nakul Srivastava
breaking: false
---

## Before

Nothing. Our GST registrations and their LUTs could be set only in the database. An export under the LUT setting can't be submitted without a LUT covering its date.

## Now

Products & prices has a fourth tab, **Seller GSTINs** (`/products?tab=seller-gstins`), for everyone with `products.view`:

- Each registration, the default first, shows its GSTIN, legal name, state, and Default or Inactive.
- Under it, its LUTs by financial year, newest first: "2026-27", the ARN, the dates, **Current** when it covers today, and **On a document** when a quotation or order carries it.
- An active registration with no LUT covering today gets a warning: an export under the LUT setting can't be submitted from it.

With `products.edit` (Admin in the mock):

- **Add LUT** opens a form with this financial year's dates filled in and the ARN to type. The ARN must be 10 to 20 letters and digits. The dates must stay within one financial year and end after they start.
- The backend's refusals land on their fields: `lut_overlap` on Valid from, `lut_duplicate` on the ARN, `lut_dates` on Valid to. Anything else goes to a toast.
- A LUT no document carries can be removed after a confirmation. `lut_in_use` shows in the dialog.

States covered:

- A skeleton while loading.
- `ErrorState` with a retry.
- An empty state.
- Async buttons with loading, success and failure.

Checked on a 390 px phone in dark mode with no sideways scroll; axe found nothing.

## Discussion

- The contract calls this "Admin › Seller GSTINs". It sits as a tab of Products & prices because it is gated on `products.view` and `products.edit`, like that page, and Products & prices is already under Admin.
- A LUT is never edited, per the contract. The remove dialog says to add it again if it was mistyped.
- No seeded backend role holds `products.edit`, so an admin grants it first (contract note). The mock gives it to Admin.
- This is part 30a. Export and sample orders on the forms and pages follow in 30b.

## Files changed

- `src/features/products/api/seller-gstins.schemas.ts`, `.api.ts`, `.queries.ts`, `.mutations.ts`: the contract, the three calls, the list query, and the add and remove mutations.
- `src/features/products/components/seller-gstins-panel.tsx`: the tab, the Add LUT form and the remove dialog, with their rules (`financialYearOf`, `lutProblems`, `lutRefusal`).
- `src/features/products/components/product-master.tsx`, `src/features/products/hooks/use-product-master-params.ts`: the new tab.
- `src/components/layout/navigation.ts`: the Products & prices description.
- `src/mocks/data/seller-gstins.ts`, `src/mocks/handlers/seller-gstins.ts`, `src/mocks/db.ts`, `src/mocks/handlers/index.ts`: the mock, with two registrations.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: MSTR-018.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/products/`: records.

## Tests

`src/features/products/components/seller-gstins.test.tsx` has 9 tests:

- `[MSTR-018] LUT rules`: financial years, ARN and date checks.
- `[MSTR-018] Seller GSTINs (contract)`:
  - the list's order;
  - next year's LUT added, then `lut_overlap`, `lut_duplicate` and `lut_dates`;
  - remove refused to a reader, `lut_in_use`, then removed.
- `[MSTR-018] SellerGstinsPanel`:
  - read-only;
  - a clash on its field, then the LUT added;
  - a LUT removed and the warning shown.

To check by hand, in the mock as Admin, open Products & prices → Seller GSTINs:

1. Add LUT with an ARN on this year's dates, and see the clash.
2. Move the dates to 2027-28 and add it.
3. Remove the Rajasthan LUT.
