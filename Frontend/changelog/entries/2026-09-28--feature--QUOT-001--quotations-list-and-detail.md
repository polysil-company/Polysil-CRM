---
date: 2026-09-28
type: feature
title: "Quotations: the list, the document and its PDF, and a lead's quotations"
dataIds:
  - QUOT-001
  - QUOT-002
  - QUOT-003
author: Nakul Srivastava
breaking: false
---

## Before

The Quotations page said "Quotations are the next module". The backend already serves quotations — drafts, sending, the PDF, the customer's answer, revisions — but nothing on screen read them, and a lead page could not show its quotations.

## Now

The read side of quotations, on the backend's contract (`backend/docs/handover/quotations-api-contract.md`). Creating, sending and deciding come in the next slices.

**The Quotations page (QUOT-001)**

- A table, newest first: the number (or **Draft** — a draft has no number until it is sent) with its version once there is more than one, the lead's inquiry number, the party and mobile, a status chip (Draft, Sent, Viewed, Negotiation, Accepted, Rejected, Expired — always labelled, never colour alone), the sales type, owner, sent date, validity and total.
- Search by number, name or mobile; filter by several statuses at once and one sales type; **Show older versions** adds the versions a revision replaced, marked "Superseded by v2". Filters and the page live in the URL, with the backend's page cursors, as on the lead list; "1–25 of 49" from the backend's count.
- States: skeleton, empty (with and without filters), error with a reference, a page link that no longer works, a page emptied since the link was made, and a notice when a refresh fails over older data.

**A quotation (QUOT-002)** — `/quotations/{id}` prints the document as the backend sends it; the screen never computes a figure.

- The number, version, status and sales type; for whom, and a link to the lead ("lead not visible" when it is outside the reader's scope).
- **Notices, most important first:** "Version 2 replaced this one" with a link; **Indicative pricing** when rates or slabs are stand-ins (the PDF carries the same banner); the customer's decision with who recorded it and the remark; a PDF that is still being prepared (the page re-reads itself every few seconds until it is ready) or that failed, with the reason; and each backend warning as a sentence.
- **Items** across the full width, in the client's own columns: quantity, rate, gross, the 1st, 2nd and 3rd discount (percentage and amount, each on the running balance — a tier shows only when a line uses it), taxable value, GST (slab, then CGST + SGST or IGST) and total. On a phone each line is a card with the same figures. Then the totals: gross, discount, taxable value, CGST and SGST (or IGST), total.
- **Party** (name, mobile, address, GSTIN when given), **Terms**, and **Details**: owner and office, channel partner or "Direct sale", place of supply and whether the tax is within or across states, the seller's registration, the price date and price list, validity, when it was sent and how many times the customer opened it, and who created it. The customer link has a **Copy** button.
- A 404 shows "Quotation not found" with a way back.

**Open PDF (QUOT-003)** — asks the backend for a link that lasts ten minutes and opens it in a new tab; the file is never fetched with the sign-in token. The tab opens on the click, so pop-up blockers allow it; if one blocks it anyway, a toast offers **Open PDF**. While the PDF renders the button reads "Preparing PDF…" and is off; a refusal says why ("The PDF is still being prepared", "The PDF couldn't be made").

**On the lead page** — a **Quotations** card lists the lead's quotations, every version, newest first: number, status, total, sent date, the older version muted and marked superseded. It shows to anyone who may see quotations.

## Discussion

- **Read first, then write.** Quotations are thirteen endpoints and a live pricing preview. The list and the document come first: they are what a manager and a field officer read every day, and the builder, send, approval and decision screens reuse everything here.
- **The screen prints, it never adds.** Money and rates stay decimal strings from the backend; totals are the backend's. Rates print without trailing zeros ("10%", "2.5%").
- **Discount tiers 2 and 3 show only when a line uses them**, so a simple quotation is not a wall of "0%" columns; the order is always the client's sheet's order.
- **The lead card shows every version**, as the contract asks: a revised quotation's history belongs to the lead.
- **Mocks follow the backend's arithmetic:** each discount tier on the running balance, rounded to the paisa before the next, GST split into CGST and SGST within the state; a test checks every mock line and total adds up. The mock has no PDFs, so its links point at a placeholder address (`TODO(QUOT-003)`).
- **Asked of the backend** (`docs/Backend-Tasks.md`): BE-015, set `PUBLIC_WEB_URL` so share links point at the app, not localhost; BE-016, say whether the dev API renders real PDFs or stores HTML.
- **Next:** the builder (QUOT-004): create and edit drafts with the product picker and live pricing, `rate_changed` handling; then send and discount approval, the customer's answer, revise and versions; then the public `/q/{token}` page.

## Files changed

- `src/features/quotations/api/` — new: the contract (`quotations.schemas.ts`), `listQuotations`, `getQuotation`, `getQuotationPdf`, and query options (the detail re-reads while the PDF renders)
- `src/features/quotations/lib/quotation-labels.ts` — new: status, sales type and PDF labels, numbers and titles, rates and quantities, warnings split into code and sentence
- `src/features/quotations/lib/quotation-table-layout.ts`, `hooks/use-quotation-list-params.ts` — new: the table layout and the list's URL state
- `src/features/quotations/components/` — new: `QuotationsTable`, `QuotationsToolbar`, `quotationColumns`, `QuotationStatusBadge`, `QuotationDetail`, `QuotationPdfButton`, `LeadQuotations`, with skeletons
- `src/app/(app)/(sales)/quotations/page.tsx` — the list instead of the placeholder; `[quotationId]/page.tsx`, `loading.tsx`, `not-found.tsx` — new
- `src/features/leads/components/lead-detail.tsx` — the Quotations card, for anyone who may see quotations
- `src/mocks/data/quotations.ts`, `src/mocks/handlers/quotations.ts` — new: quotations for the seeded leads and the three read endpoints; `src/mocks/handlers/shared.ts` — new: the error envelope and cursors, now shared with the lead handlers; `db.ts`, `handlers/index.ts`, `data/reference.ts` — registered
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — QUOT-001…003
- `Docs/Plan.md` — §9: quotations' reads connected, the rest next
- `../docs/Backend-Tasks.md` — BE-015 and BE-016

## Tests

- `src/features/quotations/lib/quotation-labels.test.ts` — `[QUOT-002]` rates and quantities without trailing zeros (and "10%", not "1%"), Draft and version titles, warnings split on the first colon
- `src/features/quotations/api/quotations.test.ts` — `[QUOT-001]` current versions newest first with the total, several statuses sent as one value and `current_only` only when off, every version of a lead's quotations, search by number; `[QUOT-002]` lines with every tier, a lead out of sight, 404; `[QUOT-003]` a signed link, 404 on a draft, 409 `pdf_pending`
- `src/features/quotations/components/quotations-ui.test.tsx` — `[QUOT-001]` skeleton then rows and total, a status filter from the URL, nothing matches, older versions marked superseded; `[QUOT-002]` the document with items, totals, decision and party, a link to the version that replaced it, the indicative-pricing banner, the PDF opened in a new tab, a PDF still being prepared, a refused PDF link closing the tab and saying why; `[QUOT-001]` a lead's quotations with the superseded one, and none
- `src/mocks/data/quotations.test.ts` — every mock quotation matches the contract, adds up to the paisa, drafts have no number, a revision shares its predecessor's number
- By hand (`npm run dev`): open Quotations, filter by Negotiation, open a v2 — the notice, the full-width items, the totals; tick Show older versions; open a lead that has quotations and see the card; try Open PDF on a ready, a preparing and a failed one. At 360px and on a wide screen, in light and dark.
