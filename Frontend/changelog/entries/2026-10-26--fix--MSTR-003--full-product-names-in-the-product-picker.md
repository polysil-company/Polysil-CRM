---
date: 2026-10-26
type: fix
title: Full product names in the product picker
dataIds:
  - MSTR-003
author: Nakul Srivastava
breaking: false
---

## Before

The client asked for this on 26 Oct: "Quotation > Product drop down > full product name not displayed". The product list in the quotation builder was only as wide as the product field, about a third of the row. Each name was cut to one line with "…", so two sizes of one pipe could read alike. Once a product was chosen, the field cut its name off too.

## Now

- **The list is wider than the field:** 32 rem on a desktop, never narrower than the field, and never past the screen's edge. On a phone it takes the screen's width.
- **Names wrap** in the list instead of being cut off, and so do the unit, HSN and code beneath them.
- **The chosen product's full name** shows in small text under the field, and the field's tooltip gives it too.
- The complaint form uses the same picker, so it gets the same fix.

## Discussion

- An input can't wrap its text, so the full name goes under the field rather than in it.
- **Not done:** making the product column wider in the row. Quantity, three discounts and GST share the row, and wrapping the list fixes the ask without squeezing them.

## Files changed

- `src/features/quotations/components/product-picker.tsx`: the list's width, wrapped names, and the full name under the field.
- `src/features/quotations/components/product-picker.test.tsx` (new).
- `Docs/Tested-Features.md`, `Docs/screenshots/quotations/product-picker-*.jpg`.

## Tests

- `product-picker.test.tsx`: after choosing "EMITTING PIPE 16 MM 40 CM SPACING 2 LPH", the full name shows under the field, and the field's `title` carries it.
- Checked in the mock with Playwright on a 1440 px desktop in light mode and a 360 px phone in dark mode. The screenshots are linked from `Tested-Features.md`.
