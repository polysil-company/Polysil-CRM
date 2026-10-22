---
date: 2026-10-21
type: feature
title: A GST slab per item, and freight
dataIds:
  - QUOT-015
author: Nakul Srivastava
breaking: false
---

## Before

Every item on a quotation or an order was taxed at its product's HSN slab, and there was no way to add freight. The backend now lets a commercial or industrial document pick each line's slab and add one freight charge (FS-069, `backend/docs/api/pricing.md`).

## Now

- **A GST dropdown on each item** in the quotation builder and the order builder, for commercial and industrial sales only.
  - It offers the slabs the admin chose (`GET /pricing/gst-slabs`, read once per screen), plus the item's own HSN slab even when that slab isn't in the list.
  - It starts on the HSN slab, marked "(HSN)". Picking another slab says "Changed from 18%" under it. Picking the HSN slab again is no change.
  - A slab is sent only for an item where one was picked, and re-sent on every save after that.
- **Freight** sits under the items: an amount before tax and an optional GST slab. Without a slab it takes the highest among the items, and the line under it says so.
  - Freight goes into the taxable value, the taxes and the total, never into gross or discount. The totals show it on its own row.
  - The amount is checked as it's typed: rupees above 0, at most two decimals. Freight with no item says "Add an item first". Either one holds the save.
  - It's sent on a new document, and on every edit of one, where an emptied box removes it.
- **The backend's refusals land on their fields:** a slab on its item (`gst_choice_not_allowed`, `gst_slab_not_offered`), and the freight's on the freight (`freight_not_allowed`, `freight_without_lines`, `freight_amount_invalid`).
- **The quotation and order pages** mark an item whose slab was picked ("Changed from HSN 18%"), and show "Freight (GST 18%)" in the totals.
- **Approvals** say "GST changed on 2 lines" on the row and in the decision dialog.
- **Company settings** gain "GST slabs an item or freight can be set to": a tick box per slab in force, at least one.
- The Council's 40 % slab joins the list of GST slabs, so tax rates can be set at 40 % too.

## Discussion

- **Subsidised, export, sample and the rest** show neither the dropdown nor freight. An export under a LUT doesn't take them either: the backend allows a choice only when the supply is taxed at home.
- **A type changed away from commercial or industrial** is cleared by the backend (warning `gst_choice_cleared`), so the builder sends neither a slab nor freight for it.
- **The PDF** is drawn by the backend. The customer's page shows only the total, which already includes freight.
- **Orders made from quotations** (consolidate) take their quotations' freight on the backend. The mock doesn't add it up, and the screen sends no freight there.
- **The mock** follows the backend's rules: the admin's list, the five refusals, freight priced like a line of one with no discount, and the default slab re-resolved on every save. It also seeds the `gst_slab_choices` setting (0, 5, 18, 40) and serves `GET /pricing/gst-slabs`.

## Files changed

- `src/features/quotations/api/` — the freight and slab fields on lines, totals, previews and saves; `GET /pricing/gst-slabs` and its query.
- `src/features/quotations/lib/builder-lines.ts`, `hooks/use-priced-lines.ts` — a picked slab per row, the freight box, what's sent, and where refusals go.
- `src/features/quotations/components/` — the GST dropdown, the freight editor, the Freight total, the "Changed from" mark (`gst-change-mark.tsx`, new) and the builder's save.
- `src/features/orders/` — the same on orders: the schema, the builder's save and the order page.
- `src/features/approvals/` — `gst_changed_lines` on a row, shown on the inbox and in the dialog.
- `src/features/settings/` — the `slabs` kind; `src/features/products/api/products.schemas.ts` — 40 %.
- `src/mocks/` — the slabs endpoint and setting, choices and freight on previews, quotations and orders, and `gst_changed_lines` on approvals.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — QUOT-015.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/quotations/` — records and screens.

## Tests

- `builder-lines.test.ts`: a slab sent only where picked and only where the sale takes it; freight sent once it reads as rupees; the freight's problems in words; a refused slab and a refused freight routed; a draft's slab and freight read back.
- `quotations.write.test.ts`, through the API: the slabs on offer; a picked slab and freight priced (freight in taxable and total, not gross); refused on a subsidised quotation; a slab off the list; a freight that isn't rupees.
- `quotation-builder.test.tsx`: the HSN slab preset and nothing sent for it; 5 % picked and ₹1,500 freight saved; a bad amount on its field; a refused slab on its item, holding the save; none of it on a subsidised quotation; a draft's slab and freight loaded and sent again.
- `order-builder.test.tsx`: 40 % on an item and freight at 5 % saved on a direct order; a refused freight on its field.
- `quotations-ui.test.tsx`: the changed item marked and the freight in the totals.
- `approvals-inbox.test.tsx`: "GST changed on 2 lines" on the row and in the dialog.
- `company-settings.test.tsx`: the slabs through the API (in force, at least one, none twice), ticked and saved, and at least one needed.
