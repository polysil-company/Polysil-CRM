---
date: 2026-10-18
type: feature
title: Export and sample orders
dataIds:
  - SO-010
author: Nakul Srivastava
breaking: false
---

## Before

The order form offered Export and Sample only as "waiting on the client's rules", and quotations could not be exports. Nothing showed an order's tax treatment, the buyer's country or the LUT.

## Now

Built to `export-sample-orders-contract.md` (FS-042). Staff only; a dealer is offered neither, and the backend answers 403 `type_staff_only`.

**Order form**

- **Export** asks for the buyer's **Country** in place of the GSTIN. The hint names the tax from the `export_tax_treatment` setting: "Export under a LUT, no IGST" or "Export with IGST". The tax is fixed once the draft is saved.
- The preview sends `tax_treatment`, so the figures are the ones the order will store. Under a LUT every line is at 0 % IGST. Under IGST each line pays IGST at its slab.
- The builder line reads "IGST 0%" or "IGST 18%" instead of an empty CGST + SGST split.
- **Sample** says what the `sample_pricing` setting makes of it, and gives the `sample_max_value` limit at list price:
  - free: every line 100 % off, a total of ₹0, and the approval runs on the list value;
  - charged: priced like a commercial order.
- An export draft can change its country. Its type stays fixed.

**Quotation form**

- **Export** on a new quotation takes the country and hides the GSTIN, priced the same way.
- An export draft stays an export, and a domestic one can't become one.

**Pages**

- The order and quotation pages show:
  - the **Country**;
  - the **Tax** with its LUT ARN, or "The LUT is taken when the order is submitted";
  - "An export: never within the state" under the place of supply;
  - on a sample, Free or Charged.
- A free sample marks each line **Free sample**, on desktop and phone.

**Place order**

- An export quotation makes an export order, its type fixed and explained.
- A domestic quotation offers commercial or industrial.

**Refusals**, shown in words:

- `export_country_required`, on the Country field;
- `export_party_gstin`;
- `export_country_not_export`;
- `lut_missing`: ask an admin to record this year's LUT in Seller GSTINs;
- `sample_over_limit`, naming the limit;
- `sample_from_quotation`;
- `type_mismatch`.

**Mock**

- Exports are taxed by the setting.
- The LUT is taken from the default registration at submit, or 422 `lut_missing`.
- Free samples are priced at 100 % off, and the limit is checked at create, edit and submit.
- A free sample's total of 0 still submits, its approval chain on the gross.
- The pricing preview honours `tax_treatment`.
- Totals now carry IGST.

Walked on a desktop in light mode and a 390 px phone in dark mode: axe found nothing, with no console errors and no sideways scroll.

## Discussion

- **The preview prices a sample domestically.** The contract makes a free sample 100 % off when it is saved. It doesn't say the preview does the same, so the builder says so in words instead of guessing.
- **The settings are staff only.** If they can't be read, the builder falls back to the backend's documented defaults (LUT, free).
- **Stacked on PR #165.** It needs the seller GSTINs and their LUTs; merge #165 first.

## Files changed

- `src/features/orders/api/orders.schemas.ts`: `tax_treatment`, `export_country`, `lut_arn`, `sample_pricing`; `StaffOrderType`; `export_country` on the create and patch requests.
- `src/features/quotations/api/quotations.schemas.ts`:
  - `TAX_TREATMENTS`, and the same fields on quotations;
  - `export_country` on its requests and `tax_treatment` on the preview;
  - Export now priced;
  - `exportCountry` on the header form.
- `src/features/quotations/lib/builder-lines.ts`: `taxTreatment` in the pricing context; `export_country` errors routed to the field.
- `src/features/quotations/lib/quotation-labels.ts`: `TAX_TREATMENT_LABELS`, `taxTreatmentText`.
- `src/features/settings/hooks/use-export-sample-settings.ts`: new, the export and sample settings with their defaults.
- Forms:
  - `src/features/orders/components/order-builder.tsx`: Export and Sample, the Country field, the refusals, `sampleHint`.
  - `src/features/quotations/components/quotation-builder.tsx`: Export and its Country field.
  - `src/features/orders/components/place-order.tsx`: export quotations make export orders.
- Pages:
  - `src/features/orders/components/order-detail.tsx`: Country, Tax, Sample and the Free sample badge.
  - `src/features/quotations/components/quotation-detail.tsx`: Country and Tax.
- `src/features/quotations/components/quotation-line-row.tsx`: an all-IGST line reads as IGST.
- Mock:
  - `src/mocks/handlers/export-sample.ts`: new.
  - `src/mocks/handlers/orders.ts`, `src/mocks/handlers/quotations.ts`, `src/mocks/handlers/settings.ts` (`mockSettings` exported) and `src/mocks/data/quotations.ts` (IGST in totals).
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SO-010.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/orders/export-*` and `sample-*`.

## Tests

- `src/features/orders/api/orders-export-sample.test.ts`, 9 tests:
  - export under a LUT (0 % IGST, not intra-state, the LUT at submit);
  - IGST by the setting;
  - the country, the GSTIN, other types and dealers;
  - `lut_missing`;
  - the preview's treatment;
  - an export quotation;
  - a free sample submitted at ₹0;
  - a charged sample;
  - `sample_over_limit`.
- `src/features/orders/components/export-sample.test.tsx`, 5 tests:
  - `sampleHint`;
  - the builder's Country in place of the GSTIN and the sample hint;
  - a dealer offered neither type;
  - the order page's country, tax and Free sample badges;
  - the quotation page's country and LUT.
- To check by hand in the mock as Admin:
  1. Open a qualified lead → New order → Export, enter a country and an item, save, then submit. The LUT appears.
  2. Make a new order as a Sample and check its lines.
  3. Make a new quotation as an Export.
