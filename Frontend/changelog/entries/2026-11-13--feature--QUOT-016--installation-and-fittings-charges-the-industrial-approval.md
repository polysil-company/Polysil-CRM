---
date: 2026-11-13
type: feature
title: Installation and fittings charges, the industrial approval ladder, and
  Polysil Sarthi
dataIds:
  - QUOT-016
  - APPR-003
  - APP-013
  - QUOT-015
author: Nakul Srivastava
breaking: false
---

## Before

- **Charges:** a commercial or industrial quotation or order could carry one charge besides its items, freight. The client also bills installation and fittings material, and had no place for them.
- **Approvals:** an industrial order climbed the same approval ladder as every other order (District, State, Regional Manager). The client runs industrial business with its own chain up to the MD / CEO.
- **Name:** the software was "Polysil CRM" / "CRM & DMS", and sign-in showed a generic line about leads and orders.

## Now

- **Other charges (QUOT-016, FS-088).** The items card of a commercial or industrial quotation or order has three optional boxes:
  - **Transportation**: the freight, named as the PDFs now print it;
  - **Installation charges**;
  - **Fittings material charges**.

  Each is rupees before tax with its own GST choice. Without a choice, installation takes 18% (a service) and the other two take the highest slab among the items. The preview prices each, says its GST and total, and adds it to the taxable value, never to gross or the discount. The totals and the saved document list each charge, such as "Installation charges (GST 18%)".

  A save sends only the charges typed in, and saving a draft's lines sends null to remove one that was cleared. A refused charge (`charge_not_allowed`, `charge_without_lines`, `charge_amount_invalid`, or a slab not on offer) shows on its own box and holds the save. A subsidised, export or sample document offers none.

- **Industrial order ladder (APPR-003, FS-089).** Approval limits has a fourth ladder, **Industrial order value**: State Manager, Regional Manager, then MD / CEO, with no District Manager step. An administrator edits it like the others, and only the MD / CEO may have no limit. Approval trails name "MD / CEO's step", and a submit that nobody can approve says it may need an MD / CEO.
- **Polysil Sarthi (APP-013).** The software is **Polysil Sarthi · Your Digital Business Partner**: beside the logo on sign-in, in the sidebar and in the browser tab. Sign-in highlights the client's vision, **To Be The Sa₹thi of Farmer's Success**, with the chariot from their banner:
  - on a wide screen, a large brand panel;
  - on a phone, a card under the form.

  The words are real text, so they stay sharp and a screen reader says "Sarthi". The Android launcher reads Polysil Sarthi from app version 0.1.3.

- Checked on sign-in at phone and desktop sizes, in light and dark.

## Discussion

- **Backend:** the backend shipped FS-088 (#258, migration 089) and FS-089 (#259, migration 090) and released them to `staging` (#260). This connects the screens to them.
- **One charge shape:** freight, installation and fittings share one shape (`FreightIn` / `FreightOut`), so the builder now keeps one set of charges. Validation, preview, save and error routing work the same for each, instead of three copies of the freight code. Freight is labelled **Transportation**, matching the backend's PDFs; the API field stays `freight`.
- **The image:** the client sent a small banner (625 × 207) with the vision baked in. Only the chariot is cut from it, round, and the words are written as text. Text stays crisp at any size; the baked-in banner would be blurry.
- **Unchanged:** the industrial ladder's amounts are the backend's stand-ins (GAP-593), and the client can change them on the screen. Offices, people and lead routing are unchanged, as the backend built it.
- **Mock backend:** the mock's seeded orders keep the general ladder; a submitted industrial order takes the new one.

## Files changed

- `src/features/quotations/lib/builder-lines.ts`: charges (`CHARGE_KINDS`, `DraftCharges`, `chargesToSave`, `chargesPresent`, `draftChargesFrom`), with errors per charge.
- `src/features/quotations/hooks/use-priced-lines.ts`: the builder keeps every charge, with its error and priced figures.
- `src/features/quotations/components/builder-parts.tsx`: **Other charges** with a row per charge; a totals row per charge.
- `src/features/quotations/components/quotation-builder.tsx`, `src/features/orders/components/order-builder.tsx`: charges on create and on a lines save.
- `src/features/quotations/components/quotation-detail.tsx`, `src/features/orders/components/order-detail.tsx`, `src/features/quotations/lib/quotation-labels.ts`: each charge in the totals (`CHARGE_LABELS`, `chargeTotalRows`).
- `src/features/quotations/api/quotations.schemas.ts`, `src/features/orders/api/orders.schemas.ts`: `installation` and `fittings` on documents, totals, the preview and the requests.
- `src/features/approvals/api/approvals.schemas.ts`, `lib/approval-limits.ts`, `lib/approval-labels.ts`, `components/approval-limits.tsx`, `components/approval-limit-dialog.tsx`: the industrial ladder.
- `src/features/quotations/lib/quotation-lifecycle.ts`: "MD / CEO" and other backend role names.
- `src/features/orders/lib/order-lifecycle.ts`: `no_approver` mentions the MD / CEO.
- `src/lib/brand.ts`, `src/components/patterns/sarthi-vision.tsx` (with stories), `src/assets/brand/sarthi-vision.webp`: the name, tagline, vision and chariot.
- `src/features/auth/components/auth-frame.tsx`, `src/app/layout.tsx`, `src/components/layout/app-sidebar.tsx`, `app-header.tsx`, `navigation.ts`, `src/features/auth/components/forced-password-change.tsx`: the new name.
- `src/features/settings/components/company-settings.tsx`: the GST slabs apply to "an item or a charge".
- `src/mocks/`: installation and fittings priced and refused as the backend does; industrial thresholds and ladder.
- `../mobile/`: launcher name Polysil Sarthi, version 0.1.3 (code 4); the Maestro launch check reads the tagline.
- `Docs/`: Data IDs, Tested-Features, Plan §9, sign-in screenshots.

## Tests

- `builder-lines.test.ts`, `[QUOT-016] installation and fittings charges`:
  - each charge is sent with its slab only when picked;
  - none goes where the sale takes none, nor one still typed wrong;
  - create sends only the charges typed in, and a lines save sends null for the rest;
  - a refusal lands on its charge;
  - a draft's charges are restored.
- `quotation-builder.test.tsx`:
  - installation at 18% and fittings at a picked 5% are saved;
  - a refused installation shows on its own box.
- `quotations-ui.test.tsx`: the document's totals list installation and fittings with their GST.
- `order-builder.test.tsx`: an industrial order saves installation and fittings.
- The QUOT-015 tests follow the rename to Transportation.
- `approval-limits.test.ts` and `approval-limits.test.tsx`, `[APPR-003]`:
  - the ladder's order and bounds, and only the MD / CEO without a limit;
  - the screen shows the ladder, and an administrator changes the Regional Manager's limit.
- `auth-frame.test.tsx`, `[APP-013]`: the name and tagline, and the vision card and panel, with spoken text for screen readers.
- By hand: sign-in in the browser at desktop and phone sizes, light and dark; screenshots are in `Docs/screenshots/auth/`.
