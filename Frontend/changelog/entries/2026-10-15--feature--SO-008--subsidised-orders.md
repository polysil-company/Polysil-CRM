---
date: 2026-10-15
type: feature
title: "Subsidised orders: placed from a subsidised quotation, and the subsidy card"
dataIds:
  - SO-008
author: Nakul Srivastava
breaking: false
---

## Before

The backend takes `order_type: "subsidised"` (FS-054). A subsidised order made from one accepted subsidised quotation takes its subsidy from it (FS-057 rule 8). It is staff only (`403 type_staff_only`).

The order carries `subsidy`:

- the material amount;
- what the scheme pays;
- what the farmer pays;
- the leads it covers, the first being the order's lead.

A draft's subsidy is changed through `PUT /orders/{id}/subsidy`. The order collects the farmer's share, at most its total, less scheme benefits (FS-055 rule 4, in the backend code).

The frontend offered only commercial and industrial orders. Placing an order from a subsidised quotation was refused with `type_mismatch`, and the order page had no subsidy.

## Now

- **Place order** on an accepted subsidised quotation:
  - fixes the type to Subsidised;
  - says where the subsidy comes from: "The subsidy comes from the quotation: ₹700.00 from the scheme, ₹300.00 from the farmer."
- **The order's Subsidy card**, on a subsidised order:
  - the material, what the scheme pays and what the farmer pays;
  - it says when the material is the order total, and when the farmer's share is material less subsidy;
  - the leads it covers, the first marked as the order's lead, and a hidden one as "a lead you cannot see".
- **Edit the subsidy**, on a draft, for staff with `sales_orders.edit`:
  - the material (empty for the order total), the subsidy, and the farmer payable (empty for material less subsidy, shown as a hint);
  - the leads stay as they are;
  - field refusals land on their fields (`subsidy.subsidy_amount`, `subsidy.farmer_payable`).
- **The draft's warnings, in words on the card:**
  - `subsidy_above_material`: the lines changed;
  - `farmer_payable_not_material_less_subsidy`: allowed, check it's what was agreed.

  These are no longer repeated in the order's notices.

- **Edit items on a subsidised draft keeps its type.** The builder used to read any type but Industrial as Commercial, and sent it whenever the header changed: the backend refuses that (`422 order_type_fixed`). A draft from quotations, or of a type the builder doesn't offer, now shows its type as fixed, and the type is sent only when it changes.
- **Refusals:**
  - `subsidy_above_material`, `payable_above_material`, `first_lead_fixed` and `lead_not_visible`;
  - `order_type_not_subsidised`, `subsidy_missing` and `quotation_subsidy_missing`;
  - `subsidised_quotation_count`, `type_mismatch` and `type_staff_only`;
  - `subsidy_scheme_changed` and `subsidy_system_changed`: revise the quotation.
- **The mock:**
  - it makes a subsidised order from one accepted subsidised quotation. Material is the calculation's cost; the subsidy includes AP's state GST, as the backend's `quotation_subsidy.for_order` does;
  - it serves and replaces a draft's subsidy, with the backend's checks;
  - it works out the defaults and warnings again when the lines change;
  - it refuses a type change on an order from quotations or a subsidised one (`order_type_fixed`).
- Checked on a desktop in light mode and a phone in dark mode: from a subsidised lead, the quotation and its subsidy, sent without a message and accepted, then the order placed, its card, and the subsidy edited. axe found nothing.

## Discussion

- **Not part of go-live** (the user, 13 Oct); built in the plan's order.
- **Stacked on #141** (subsidised quotations), which is stacked on #140. Merge #140, then #141, then this; retarget each to `integration` before merging.
- **A subsidised order typed in** is plan item 17b: the order builder with several leads (1 to 50), the material, the subsidy and the farmer payable, and no `lead_id` (`lead_from_subsidy`). The mock still answers it with `order_type_unsupported` (a `TODO(SO-008)` marks it).
- **The leads on a draft can't be changed here yet.** The edit keeps `lead_ids` as they are. Adding or removing leads comes with item 17b's lead picker.
- **The handover says a subsidised order is never made from a quotation; the backend code allows it** (`_check_subsidy_shape`, `quotation_subsidy.for_order`). The frontend follows the code.
- **The handover also says a subsidised order's `payable` is not the farmer's share; the code bases it on the farmer's share** (at most the total, less scheme benefits: `get_order`, FS-055 rule 4). The card says what the code does. The frontend doesn't show `payable` yet.
- **Not yet checked on staging.**

## Files changed

- `src/features/orders/api/orders.schemas.ts`, `orders.api.ts`, `orders.mutations.ts`: the subsidy block, Subsidised from a quotation, `setOrderSubsidy` and `useSetOrderSubsidy`.
- `src/features/orders/components/order-subsidy.tsx`: new, the card and the edit dialog.
- `src/features/orders/components/order-detail.tsx`: the card, and its warnings left out of the notices.
- `src/features/orders/components/place-order.tsx`: Subsidised for a subsidised quotation.
- `src/features/orders/lib/order-lifecycle.ts`: the refusals.
- `src/features/orders/components/order-builder.tsx`: a fixed type shown as fixed, and sent only when changed.
- `src/mocks/handlers/orders.ts`, `src/mocks/db.ts`: subsidised orders from quotations, `PUT /orders/{id}/subsidy`, and the block worked out again on a lines change.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SO-008.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/orders/order-subsidy-*`: records and screens.

## Tests

- `src/features/orders/components/order-subsidy.test.tsx`:
  - the order takes its subsidy from the accepted subsidised quotation;
  - a quotation of the wrong type, one without its subsidy, and a dealer are refused;
  - a draft's amounts are changed: material left out is the order total, and the payable is derived;
  - a new first lead, a subsidy above the material, and an order that isn't subsidised are refused;
  - placing it: the type is fixed to Subsidised, the subsidy is named, and the draft opens;
  - the card: the amounts and the lead, and new amounts saved;
  - a payable that isn't material less subsidy is shown, and one above the material is refused.
- `src/features/orders/components/order-builder.test.tsx`: a subsidised draft keeps its type when its header changes (the mock now refuses a type change with `order_type_fixed`, as the backend does).
- Walked through in the mock: desktop light and phone dark.
