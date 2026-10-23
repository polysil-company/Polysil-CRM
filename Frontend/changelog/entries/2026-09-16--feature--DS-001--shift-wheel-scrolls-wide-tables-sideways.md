---
date: 2026-09-16
type: feature
title: Shift and the mouse wheel scroll a wide table sideways
dataIds:
  - DS-001
author: Nakul Srivastava
breaking: false
---

## Before

A table with more columns than fit scrolled sideways only by dragging its scrollbar or by swiping on a trackpad. On a mouse, the wheel moved the page and the far-right columns — amounts, follow-up dates, actions — stayed out of reach.

## Now

Holding Shift and turning the wheel over a table scrolls its columns sideways, the same gesture browsers use on a page. It is built into `DataTable`, so every table gets it: leads today, quotations and orders as they land.

- Only vertical wheel movement is redirected. A trackpad swipe, or a mouse that already sends a sideways wheel, is left to the browser.
- At the first or last column the wheel returns to the page, so a long table still scrolls down without letting go of Shift.
- A table whose columns already fit ignores Shift entirely.
- Nothing changes for keyboard or touch: tabbing through a row still brings cells into view, and phones keep swiping.

## Discussion

- **In the shared table, not each screen.** `DataTable` owns its scroll area, so the behaviour belongs there rather than in the leads table.
- **A generic hook** (`useShiftWheelScroll`) holds it, because any scroll area with hidden width can use it later — a wide chart or a filter row.
- **The listener is non-passive**, which is what lets it replace the page's vertical scroll. It is attached directly to the element rather than through React's `onWheel`, which React registers as passive and where `preventDefault` would do nothing.
- **Edges fall through on purpose.** Swallowing the wheel at the last column traps the page: the reader holds Shift, the table is finished, and nothing moves.
- **Not done:** a keyboard equivalent. Tabbing scrolls the container natively, so this is a mouse convenience, not the only way through a table.

## Files changed

- `src/hooks/use-shift-wheel-scroll.ts` — the hook
- `src/components/patterns/data-table/data-table.tsx` — the table's scroll area uses it
- `Docs/Design-System.md` — how wide tables scroll

## Tests

- `src/hooks/use-shift-wheel-scroll.test.tsx` — `[DS-001] useShiftWheelScroll`: Shift scrolls sideways, a plain wheel is left alone, the edges fall through to the page, and a table that fits ignores it
- By hand: `npm run dev` → open Leads, narrow the window until columns are cut off, and hold Shift while scrolling over the rows. Check that the page still scrolls at the last column, and that a trackpad swipe behaves as before.
