---
date: 2026-10-23
type: fix
title: A scheme test that raced its save
dataIds:
  - SCHM-002
author: Nakul Srivastava
breaking: false
---

## Before

On the `integration` → `staging` pull request (#202), CI failed once in `schemes.test.tsx`, at "adds a product category as a target, by its id". The same commit passed on the `integration` run. The test waited for the "Scheme created" toast, then read the mock database for the new scheme, and found nothing.

## Now

Both scheme-creating tests wait for the scheme to be in the mock database before reading it. Only the tests changed; the app is untouched.

## Discussion

- **The cause:** sonner keeps its toasts in a module-level store. The test above it also shows "Scheme created", so that toast can still be there when the next test's toaster mounts. The wait then finishes before this test's save has answered.
- **On a busy CI runner** the read lost the race. Waiting for the record itself removes the race whatever toasts remain.
- **This is not a skipped or retried test:** both assertions are unchanged.

## Files changed

- `src/features/schemes/components/schemes.test.tsx`: wait for the saved scheme in both creation tests.

## Tests

`src/features/schemes/components/schemes.test.tsx`: 14 tests, passing three runs in a row locally.
