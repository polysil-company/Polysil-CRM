---
date: 2026-09-16
type: design
title: The leads table shares leftover width instead of pooling it in one column
dataIds:
  - LEAD-001
  - DS-001
author: Nakul Srivastava
breaking: false
---

## Before

On a large monitor the leads table left a long empty band between Customer and Status — on a 2560px screen, roughly 500px of nothing. Customer was the table's only flexible column, so every spare pixel went there. On a laptop, where there is no width to spare, the table looked right.

## Now

Crops and Owner are flexible too, so the leftover width is split three ways: each column gains a little and the long gap goes. The floors stay where they were (224px), so a laptop, a tablet and a phone are unchanged — the split only happens when there is width to spare.

## Discussion

- **Why not cap the columns and park the leftover at the right edge?** That removes the in-between gaps completely, and it is what Airtable and Attio do. It also means fixing Customer at a set width, and at about 1280px the columns then add up to more than the panel — so a screen that reads well today would gain a horizontal scrollbar. Not worth trading a working laptop layout for a wide-monitor nicety. If you want the tighter look, this is the change to make, and the leads table is where to start.
- **Why not cap the whole table?** Centring a capped table leaves dead space at both edges of a full-bleed panel, which reads as a mistake rather than a margin.
- **Still air on very wide screens.** Three columns share the slack, so each gets about a third of what Customer used to hold. The way to remove it rather than divide it is to show more in that space — more crop tags, a phone number under the name — which is a content decision, not a layout one. Raised, not taken.
- **Tested by eye.** How a browser divides leftover width between table columns is not something a unit test can see; the test guards the rule that more than one column is flexible.

## Files changed

- `src/features/leads/lib/lead-table-layout.ts` — Crops and Owner are `fill`
- `src/components/patterns/data-table/table-features.ts` — what `fill` means, and why it belongs on more than one column
- `Docs/Design-System.md` — the same rule for every table

## Tests

- `src/features/leads/lib/lead-table-layout.test.ts` — `[LEAD-001] leads table layout`: more than one column is flexible, and every column has a width
- By hand: open Leads on the large monitor and check the space between Customer and Status. Then at 1280px and 1440px confirm nothing moved, and at 360px that the table still scrolls sideways.
