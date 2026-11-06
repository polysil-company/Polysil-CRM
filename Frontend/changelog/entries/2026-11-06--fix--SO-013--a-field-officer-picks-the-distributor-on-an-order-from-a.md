---
date: 2026-11-06
type: fix
title: A field officer picks the distributor on an order from a lead
dataIds:
  - SO-013
  - SO-012
author: Nakul Srivastava
breaking: false
---

## Before

A field officer starting a sales order from a lead couldn't choose the distributor. The order builder showed no dealer or distributor field on an order from a lead, and silently sent the lead's own channel partner, or none.

## Now

- **From a lead:** staff get **Through a dealer or distributor**, set to the lead's channel partner. They can pick another dealer or distributor, or clear it.
- **The farmer stays the party:** picking a partner only changes the rates; the farmer's name and details stay. `partner_id` is sent with `lead_id`.
- **Help text:** both partner fields now say only partners in your area are listed, so a missing distributor isn't a mystery.
- Dealer users and edits are unchanged.

## Discussion

- The client reported that a field officer couldn't choose a distributor on a new sales order (6 Nov). The frontend gap was the order from a lead; it is fixed here.
- The search only lists partners in the officer's own area (`GET /lookups/partners` row scope), so a distributor serving a wider area may still not show. That rule is the backend's and the client's to decide: **BE-043**.

## Files changed

- `src/features/orders/components/order-builder.tsx` — the partner field on orders from a lead, starting at the lead's partner; the farmer stays the party.
- `src/features/orders/components/order-builder.test.tsx` — two SO-013 tests.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`, `Docs/Tested-Features.md` — SO-013.
- `../docs/Backend-Tasks.md` — BE-043.

## Tests

- `order-builder.test.tsx`: "[SO-013] on an order from a lead, picks the distributor it goes through, keeping the farmer as the party" and "[SO-013] starts an order from a lead at the lead's own channel partner".
- By hand: sign in as a field officer, open a lead, **Create sales order**, pick a distributor, save, and check the order shows the farmer as the party and the distributor's rates.
