---
date: 2026-10-30
type: feature
title: Visits take the location by themselves once allowed
dataIds:
  - TRK-003
  - TRK-004
author: Nakul Srivastava
breaking: false
---

## Before

To check in or out of a visit, the person tapped **Locate me** every time, even after allowing location long ago. The check-out form also said "Your location is taken when you check in".

## Now

- **Location already allowed:** opening check-in or check-out takes a fresh fix straight away. The client asked for this on 30 Oct.
  - In the Android app, "allowed" means Android's own permission; in a browser, it means the site's.
  - The accuracy and **Locate again** still show, so a rough fix taken indoors can be taken again before saving.
- **Not allowed yet:** the form waits for a tap on **Locate me**, as before, so Android's permission question only ever follows the person's own tap.
- Check-out says "Your location is taken when you check out."

## Discussion

- **Why not ask on open as well:** a permission prompt that appears unasked as a form opens is easy to refuse by reflex, and a refusal is then sticky in Android. Asking only after a tap keeps it intentional. After that, nothing is asked again.
- **Freshness:** each form takes a new fix (`maximumAge: 0`), never a remembered one, so a check-in records where the person is now.
- **Fallback:** if the permission can't be read (an older browser, an error), the form behaves as before and waits for **Locate me**.

## Files changed

- `src/features/tracking/hooks/use-browser-fix.ts`: `locationAlreadyAllowed`, and `useBrowserFix({ autoWhenAllowed })`.
- `src/features/tracking/components/fix-panel.tsx`: `action` ("check in" or "check out") in the waiting line.
- `src/features/tracking/components/check-in-form.tsx`, `open-visit.tsx`: take the location by themselves.
- `src/features/tracking/components/visits.test.tsx`, `Docs/Tested-Features.md`.

## Tests

`visits.test.tsx`:

- with location allowed, check-in and check-out both show "to within 12 m" without a tap, and **Locate again** is offered;
- with location not yet allowed, the form shows **Locate me**, says what the location is for, and holds no fix.
