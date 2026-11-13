---
date: 2026-10-25
type: test
title: An HSN test that raced a leftover toast
dataIds:
  - MSTR-005
author: Nakul Srivastava
breaking: false
---

## Before

"Creates the product, then sets its HSN" (PR #191) failed in CI on #208, and the next test failed after it.

- The test waited for the "Product added" toast, then checked that both calls had gone.
- Sonner keeps toasts in a module store across tests, so the earlier "adds a product" test's toast was already on screen. The check ran before this test's HSN call had started.
- That late call was then caught by the next test's call recorder. This is the same cause as SCHM-002 (#203).

## Now

The test waits on what it checks:

- both calls;
- the HSN saved in the mock;
- the row's "No HSN" badge gone.

No screen code changes.

## Discussion

A shared fix, clearing sonner's store after every test, would touch every toast test. Waiting on the outcome is local and matches #203.

## Files changed

- `src/features/products/components/products-ui.test.tsx`

## Tests

The file's 23 tests pass. The failure only shows under CI load: the CI log of #208's second run showed `[POST]` without the `PUT`, and the next test caught the leftover `PUT`.
