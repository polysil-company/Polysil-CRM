---
date: 2026-11-11
type: fix
title: "Day pickers: arrows as tall as the date field on phones"
dataIds:
  - TRK-002
  - TRK-005
  - TASK-001
author: Claude
breaking: false
---

## Before

- **The report:** on a phone, the day picker on a person's route (Team map → a person) had arrow buttons shorter than the date field between them.
- **Why:** on touch screens a field grows to the 44 px touch height (`pointer-coarse:h-control-lg` in `Input`), but the arrow buttons kept their desktop size: 36 px (`icon-md`), or 30 px on Tasks (`icon-sm`).
- **Same mismatch elsewhere:** My visits has the same day picker, and the Tasks page has a smaller one.

## Now

- **Phones:** on a touch screen, the arrows on all three day pickers are 44 px, the same height as the date field, and a full-size touch target.
- **Desktop** is unchanged.

## Discussion

- **Only these arrows, not every icon button.** Making all `icon-md` buttons 44 px on touch would change many other layouts at once. These three are the arrows that sit beside a date field.

## Files changed

- `src/features/tracking/components/route-day.tsx`, `src/features/tracking/components/my-visits.tsx`, `src/features/tasks/components/tasks-view.tsx`: `pointer-coarse:size-control-lg` on the day arrows.
- `Docs/screenshots/tracking/route-day-phone-light.jpg`, `my-visits-phone-light.jpg`.

## Tests

- **Measured:** on a touch phone in the mock (390 × 844, touch on), the arrows and the date field are the same height on the route and on My visits. Screens are linked above.
- **Unit tests:** the tracking and tasks tests pass (104).
