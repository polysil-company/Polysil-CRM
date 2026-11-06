---
date: 2026-09-28
type: feature
title: "Quotations: make and edit a draft, priced live"
dataIds:
  - QUOT-004
  - QUOT-005
  - MSTR-003
author: Nakul Srivastava
breaking: false
---

## Before

Quotations could be read — the list, the document, its PDF — but not made. A lead page had no way to start a quotation, and a draft could not be changed.

## Now

The quotation builder, on the backend's contract (`backend/docs/handover/quotations-api-contract.md`). Sending, approval and the customer's answer come in the next slice.

**Start a quotation (QUOT-004)** — the lead's **Quotations** card has **New quotation**, which opens `/quotations/new?lead=…`. It shows only to people who may create quotations. A lead that can't be quoted says why instead: "Qualify the lead first" (new, contacted), "Reopen the lead first" (lost), "The lead is dormant"; a merged lead points to the lead it was merged into.

**Items** — each item is a product, a quantity and up to three discounts, each a percentage of the balance after the one before, in the client's sheet's order.

- **The product picker (MSTR-003)** searches the catalogue on the server as you type, and names each product's unit, HSN and code, since two sizes of one pipe read alike. The quantity shows the product's unit.
- **Live pricing (QUOT-005)** — once typing pauses, the whole basket is priced by the backend. Under each item: rate, taxable value, GST (CGST + SGST, or IGST, as the backend split them) and total, with **Indicative rate** when the rate or slab is a stand-in. The screen never adds money up; older figures stay on screen, dimmed, while new ones arrive.
- A row says what it still needs ("Choose a product", "Enter a quantity above 0", "Discounts are percentages from 0 to 100"). Empty rows are ignored.

**Customer and terms** — sales type (commercial or industrial; the other types wait on the client's rules), the party's name, mobile, GSTIN and address (filled from the lead), and terms. Validated in the browser and again by the backend, whose field errors land on the right field or item.

**Summary** — gross, discount, taxable value, CGST and SGST (or IGST) and total, from the backend; its pricing notes; and **Save draft**. Save is off until every item is complete and priced, and says why.

**Saving** — a draft has no number until it is sent. The save carries the price row and tax rate the preview used, so the backend can tell when prices changed since. Then:

- **`rate_changed` (409):** "Prices changed since you priced this" — the affected items say "Rate: now …", the basket is priced again, and the next save is a new request.
- "This lead can't be quoted yet", "This lead is closed", "That sales type isn't priced yet", "This quotation has moved on" (sent or changed by someone else), and field errors on their fields.
- A retry of the same save reuses its `Idempotency-Key`, so a double click or a timeout never makes two drafts.
- On success: "Draft saved", and the draft opens.

**Edit a draft** — the draft's page has **Edit draft**, which opens `/quotations/{id}/edit` with its items and header. Saving sends the header only when it changed, then the items. A quotation that was sent says it is revised, not edited.

## Discussion

- **The backend prices, the screen asks.** Every figure comes from `POST /pricing/quote-lines`; nothing is multiplied or added in the browser. Pricing runs 400 ms after typing stops and cancels a preview that is no longer needed.
- **Why the save carries `price_list_item_id` and `gst_rate_id`:** the contract answers `rate_changed` when either moved since the preview, so a person never saves figures they didn't see.
- **Discount above the owner's limit is not blocked here.** The contract lets a draft carry any discount and asks for approval at send; the edit screen repeats the last save's discount and limit. The send and approval screens come next.
- **Mocks follow the contract:** products, preview, create, header and lines, `lead_not_qualified`, `sales_type_unsupported`, `rate_changed` (bump `mockDb.priceVersion`), replays by `Idempotency-Key`, and refusing to edit a sent quotation.
- **Next:** send and discount approval; accept, reject and negotiation; revise, versions and delete; then the public `/q/{token}` page.

## Files changed

- `src/features/quotations/api/quotations.schemas.ts` — products, the pricing preview, create, header and lines requests, the header form, `QuotationLine` shared by the document and the preview, and the draft's discount against the owner's limit
- `src/features/quotations/api/quotations.api.ts`, `quotations.queries.ts` — `searchProducts`, `previewQuoteLines`, `createQuotation`, `patchQuotation`, `replaceQuotationLines`, with query options; `quotations.mutations.ts` — new: create and update, refreshing the document, the lists and the lead's timeline
- `src/features/quotations/lib/builder-lines.ts` — new: rows, what each still needs, the preview request, the lines to save, and routing the backend's field errors to fields and rows
- `src/features/quotations/lib/quotation-labels.ts` — why a lead can't be quoted yet
- `src/features/quotations/components/` — new: `QuotationBuilder`, `QuotationLineRow`, `ProductPicker`, `NewQuotation` and `EditQuotation`; `LeadQuotations` — **New quotation**; `QuotationDetail` — **Edit draft**
- `src/features/leads/components/lead-detail.tsx` — passes the lead's stage to its Quotations card
- `src/app/(app)/(sales)/quotations/new/` and `[quotationId]/edit/` — new routes
- `src/mocks/data/quotations.ts`, `src/mocks/handlers/quotations.ts`, `src/mocks/db.ts` — the products, pricing and the three writes
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — QUOT-004, QUOT-005, MSTR-003
- `Docs/Plan.md` — §9: the builder connected

## Tests

- `src/features/quotations/lib/builder-lines.test.ts` — `[QUOT-004]` what a row still needs; `[QUOT-005]` only finished rows priced, empty discounts sent as 0, partner and price date when known; `[QUOT-004]` priced lines matched to rows, saved lines carry the price row and tax rate, a draft read back into rows, backend field errors routed to fields and rows in words
- `src/features/quotations/api/quotations.write.test.ts` — `[MSTR-003]` search by description, and nothing found; `[QUOT-005]` a basket priced with its tiers and tax split; `[QUOT-004]` a draft with no number and a replay by key, `lead_not_qualified`, `rate_changed` after the price list moved, header and lines edited, a sent quotation refused
- `src/features/quotations/components/quotation-builder.test.tsx` — `[QUOT-004]` an item priced as it is entered, then saved and opened; `rate_changed` explained, re-priced and saved; Save off until an item is complete; no lead, a lead not yet qualified; a draft loaded for editing, a sent quotation not edited
- `src/features/quotations/components/quotations-ui.test.tsx` — the lead's Quotations card with the lead's stage
- By hand (`npm run dev`): open a qualified lead → New quotation; add a UPVC pipe with 10% and 5%, and an HDPE lateral (indicative rate); watch each item and the totals price; save and see the same figures on the draft; Edit draft, change the terms and a quantity, save. Try a new lead (explained). `rate_changed` needs the price list to move mid-edit, so the tests cover it. At 360px and on a wide screen, in light and dark.
