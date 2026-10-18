---
date: 2026-10-18
type: feature
title: Visits on the web
dataIds:
  - TRK-003
  - TRK-004
  - TRK-005
author: Nakul Srivastava
breaking: false
---

## Before

Visits could only be recorded from the Android app, which isn't built yet. On the web, a manager could see visits on a route, but nobody could check in. The app's own security header also stopped every page from reading the location.

## Now

Built to `field-tracking-contract.md` §3 (Visits) and the generated `tracking.md`. Checking in and out is the contract's "app and web" part.

**My visits** (`/visits`, TRK-005)

- A **Visits** item under Sales for staff who track (`tracking`).
- The day is in the URL, with the day before, a date field and the day after (never past today).
- Each visit shows its time, what it was to (a lead, linked), its outcome, the time spent, photos, a note, and whether it closed by itself after 12 hours.
- Loading, empty ("No visits yet today", or "No visits this day"), error with a retry, and **Show more**.
- A role that doesn't track is told so.

**Checking in** (TRK-003)

- **Check in** asks what is being visited: **A lead** (search by farmer, mobile or inquiry number), **A dealer**, or **Another place** by name.
- **Locate me** asks the browser for the location, on the user's tap, as browsers prefer. It shows how accurate the fix is and warns above 100 m. A blocked location, a browser without it, or a failure each say what to do.
- The first time, the consent text from `/me/tracking-config` is shown, with **I agree** or **Not now**. **I agree** records it (`POST /tracking/consent`) and continues to the check-in.
- The visit id is made in the browser. Every new try gets a new id and key, as the contract asks after a 4xx.
- **Refusals:**
  - `visit_open`: says another visit is still open and offers **Open that visit** (`?visit=`);
  - `consent_required`: asks for consent;
  - a lead or dealer the user can't see: asks for another;
  - field errors land on the form.

**The open visit** (TRK-004)

- A card at the top: what it is, since when, its photos ("1 of 3"), and **Check out**.
- **Add photo** opens the camera on a phone (`capture`), or the file picker on a computer. The type and the 10 MB limit are checked first, then `photo_limit`, `photo_window_closed` and 413 are explained. **Photo 1** and so on open a ten-minute link.
- **Check out** asks how it went (**Met**, **Not available**, **Follow up**, **Other**), takes an optional note and the location again, then closes the visit.
  - When the policy requires a photo and there is none, the form says so before sending.
  - `photo_required` and `visit_closed` are explained.

**Security header**

- `Permissions-Policy` now allows `geolocation=(self)` instead of `geolocation=()`, so this app's own pages can ask for the location; embedded frames still can't.
- Camera and microphone stay off: the photo picker doesn't need them.
- The CSP TODO now notes that the map's tile host will need `img-src`.

**Mock**

- The consent version each person accepted is kept.
- One open visit at a time, a lead and a dealer never together, and a place name when neither is given.
- The same id answers with the same visit.
- Up to three photos within 24 hours, opened as the file itself.
- Check-out once; the day's list for "me".

Walked as a field officer on a desktop in light mode and a 390 px phone in dark mode, with the browser's location granted: consent, check in at a place, a photo, check out as Met. Axe found nothing, with no console errors and no sideways scroll.

## Discussion

- **The walk found two bugs, both fixed here.**
  - The `geolocation=()` header blocked the location everywhere, in production too.
  - The first photo upload ran before the chosen file was stored. The file is now passed straight to the upload. The UI test adds a photo, so this stays caught.
- **CI runs Node 24; this sandbox runs Node 22.** Node 24's form parser won't build a `File` while jsdom owns the global one, so the mock's photo upload answered 500 in CI's component tests. It now reads the multipart body by hand when that happens, and the tests pass on both versions.
- **Locate me is a tap, not automatic.** Browsers show the permission prompt more willingly after a tap, and the user sees why it's asked.
- **Photos of earlier visits can't be listed.** The contract returns a photo's id only when it's uploaded, so the card opens the photos added in this session. A visit's count is always shown.
- **This is part 35b.** The tracking settings and the view log (35c) follow.

## Files changed

- `src/features/tracking/api/visits.schemas.ts`, `.api.ts`, `.queries.ts`, `.mutations.ts`: new, the config, consent, check-in, check-out, photos and list.
- `src/features/tracking/hooks/use-browser-fix.ts`: new, the browser's location with every outcome.
- `src/features/tracking/hooks/use-day-param.ts`: new, the day in the URL, shared with the route page.
- `src/features/tracking/components/check-in-form.tsx`, `open-visit.tsx`, `my-visits.tsx`, `fix-panel.tsx`, `visit-lead-picker.tsx`: new.
- `src/features/tracking/components/route-day.tsx`: uses the shared day hook.
- `src/app/(app)/visits/page.tsx`: new route; `src/components/layout/navigation.ts`: the Visits item.
- `next.config.ts`: `geolocation=(self)`.
- Mock: `src/mocks/handlers/visits.ts` (new), `src/mocks/db.ts`, `src/mocks/handlers/index.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: TRK-003…005.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/tracking/visit*`.

## Tests

`src/features/tracking/components/visits.test.tsx`, 7 tests:

- `[TRK-003] Checking in (contract)`:
  - consent asked, check-in, the same id replayed, `visit_open` naming the open visit, a blank place refused;
  - a role that doesn't track.
- `[TRK-004] Photos and check-out (contract)`:
  - three photos, then `photo_limit`, a link, check-out once, then `visit_closed`, and the day's list;
  - a photo's type and size checked first.
- `[TRK-005] MyVisits`:
  - consent, check-in at a place with the location, a photo, check-out as Met;
  - a blocked location explained, with Check in disabled;
  - a role without tracking.

To check by hand in the mock, as a field officer (Preview as role → Field officer):

1. Open Sales → **Visits** → **Check in**, agree, choose **Another place**, and select **Locate me**.
2. Check in, add a photo, then **Check out** as **Met**.
