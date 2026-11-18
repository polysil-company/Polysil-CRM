---
date: 2026-11-17
type: fix
title: An item over the ₹10 crore ceiling says so in rupees, with no old figures
  beside it
dataIds:
  - QUOT-017
  - QUOT-004
  - SO-005
author: Nakul Srivastava
breaking: false
---

## Before

The client's screenshot of quotation POL/GJ/2026-27/00013 (17 Nov) shows the problem. Item 1 was 42,800 m at ₹3,472.95, about ₹14.86 crore, which is over the backend's ceiling of ₹9,99,99,999.99 for one line.

- The row said "Quantity: a line total may not exceed 99999999.99; this one is 148642260.00": unformatted figures, labelled as a quantity problem.
- Beside it the row still showed Rate, Taxable, "GST 5%" and Total. Those were the preview's figures for 42 m before the GST was changed, and they read as this item's price.
- A document over the ceiling had no field of its own, so it fell to a generic "couldn't price" with a **Price again** button that can never help.

## Now

- **Item over the ceiling:** "This item comes to ₹14,86,42,260.00 before discount; one item can be at most ₹9,99,99,999.99. Split it across items or documents."
- **Document over the ceiling:** "The total comes to more than ₹9,99,99,999.99, the most one quotation or order can be. Split it across documents." It shows above the totals, with no **Price again**. A save the backend refuses on the total says the same at the top of the form.
- **No old figures:** a row the preview refused shows none. The figures from a quantity half typed, or from before a GST change, are gone.
- **Save:** stays off with "Fix the pricing first." until the item or the total fits.
- Quotations and orders share the builder, so both get this.

## Discussion

- The ceiling is the backend's (`MAX_LINE_TOTAL`, `MAX_DOCUMENT_TOTAL` in `tax.py`), an overflow guard ("Rule 11"), not a client rule. The money columns hold far more.
- **BE-044** asks the backend to raise both, for example to ₹999 crore. Until it ships, a quotation over ₹10 crore has to be split.
- The rupee wording is drawn from the backend's message text, since the error has no separate fields for the amounts. If the wording changes, the screen falls back to the backend's own sentence.

## Files changed

- `src/features/quotations/lib/builder-lines.ts`: the ceilings in rupees; a document-level refusal (`document`) beside the rows' and the charges'.
- `src/features/quotations/hooks/use-priced-lines.ts`: `documentError`; a document refusal is no longer a pricing failure to retry.
- `src/features/quotations/components/builder-parts.tsx`: a refused row shows no figures; the document's refusal above the totals; save blocked by it.
- `src/features/quotations/components/quotation-builder.tsx`, `src/features/orders/components/order-builder.tsx`: a save refused on the total says so.
- `src/mocks/handlers/quotations.ts`: the mock refuses a line and a document over the ceiling, as the backend does.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`, `Docs/Tested-Features.md`: QUOT-017.
- `../docs/Backend-Tasks.md`: BE-044.

## Tests

- `builder-lines.test.ts`, `[QUOT-017]`: the line ceiling in rupees on its row, and the document ceiling on the document.
- `quotation-builder.test.tsx`, `[QUOT-017]`:
  - 1,000,000 m of pipe says its value and the ceiling, the 10 m figures go, and save stays off;
  - a document over the ceiling says so without **Price again**.
