---
date: 2026-10-18
type: feature
title: The farmers' portal
dataIds:
  - FARM-001
  - FARM-002
  - FARM-003
author: Nakul Srivastava
breaking: false
---

## Before

A farmer couldn't see anything themselves. A farmer who signed in with their mobile would have landed in the staff app, where the backend refuses every call to a farmer.

## Now

Built to `consumer-portal.md` (FS-044) and the generated `portal.md`, including the portal ratings (FS-060). It is off by default; the admin switches it on in Company settings. The portal gets a new Data ID domain, `FARM`.

**Switching it on**

- **The farmers' portal** in Company settings now carries the cost warning: "On, every customer's number can be sent a WhatsApp sign-in code, and each code is paid for. Off signs every farmer out."

**Signing in**

- A farmer signs in with the existing **Mobile number** sign-in: their number, then the WhatsApp code.
- A farmer's session works only in the portal, so the staff app sends them straight to `/portal` (`FarmersToPortal`).
- Staff or a dealer who opens `/portal` is told it is the farmers' portal, with a link back to the main app.

**The portal** (`/portal`, FARM-001)

- Its own simple frame: the brand, "Your irrigation record", the theme switch and **Sign out**, in one narrow column. There is no sidebar or search.
- "Namaste, {name}" with their mobile, village and area.
- **Your orders**: each order's status in words, its total (or "Through your dealer"), when it was placed, and every dispatch with its challan.
- **Your quotations**: status, total (or "Through your dealer"), sent and valid until. **Open** opens the page they were sent, in a new tab.
- **Your complaints**: status and when it was raised.
- **Your enquiries**: number, system, date and status.
- Each list has its own loading, empty and error state.
- While the portal is off, it says "The portal is closed for now" and to call their officer or dealer.

**Consent** (FARM-002)

- **Updates from Polysil** shows whether they agreed to be contacted, and when. **Yes, contact me** and **Stop updates** switch it (`aria-pressed`).

**Rating** (FARM-003)

- **Rate** appears beside an order with a dispatch and beside a closed complaint.
- The form asks for 1 to 5 stars, with words for each, and optional words of their own. It says a rating can't be changed later.
- Once rated, the row shows the stars with "Your rating", or "Rated with our officer" when an officer recorded it for them.
- If the backend refuses (`not_rateable`, `rating_exists`), the form says why in words and the button goes.

**Mock**

- A customer's number signs in by OTP as that farmer, with code `123456`. Signing out, staff sign-in and **Preview as role** end that session.
- While a farmer is signed in, every route outside `/auth` and `/portal` answers 403 `consumer_not_allowed`.
- `/portal` answers `portal_off` while the setting is off, and `not_a_consumer` to staff and dealers.
- The lists come from the farmer's own leads. A dealer's documents have no total or link. Consent is recorded on the portal channel, and ratings follow the contract.

Walked on a desktop in light mode and a 390 px phone in dark mode: Admin switches the portal on and signs out, Hitesh Jadeja signs in by OTP, rates his installation and agrees to updates. The portal-off notice was checked on a phone in light mode. Axe found nothing and there was no sideways scroll. The only console line was the browser noting the 403 while the portal is off.

## Discussion

- **One sign-in page for everyone.** The contract reuses the OTP endpoints, so a farmer uses the existing **Mobile number** sign-in and is sent on by session type. Question 10.4 suggests a separate app; this frame keeps the portal apart without a second sign-in to maintain.
- **Read-only, plus consent and ratings.** Question 10.3 (what farmers should do there) is unanswered, so this round does no more, as the contract says.
- **The mock keeps the farmer in browser storage.** Like the previewed role, so a reload keeps the session. The portal setting resets on reload, so a demo switches it on first.

## Files changed

- `src/features/portal/`: new.
  - `api/portal.schemas.ts`, `.api.ts`, `.queries.ts`, `.mutations.ts`: the contract, the eight calls, queries and the consent and rating mutations.
  - `lib/portal-labels.ts`: statuses in words, and the refusals.
  - `components/portal-home.tsx`: the page.
  - `components/portal-rating-form.tsx`: rating.
- `src/components/layout/portal-shell.tsx`, `src/components/layout/farmers-to-portal.tsx`: new, the portal's frame and the redirect out of the staff app.
- `src/app/(portal)/portal/layout.tsx`, `page.tsx`: new routes; `src/app/(app)/layout.tsx`: `FarmersToPortal`.
- `src/features/settings/components/company-settings.tsx`: the cost warning.
- `src/lib/dev/mock-settings.ts`: the mock farmer session.
- Mock: `src/mocks/handlers/portal.ts` (new), `src/mocks/handlers/auth.ts`, `src/mocks/handlers/index.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: the `FARM` domain and FARM-001…003.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/portal/`.

## Tests

`src/features/portal/components/portal.test.tsx`, 10 tests:

- `[FARM-001] The farmers' portal (contract)`:
  - off by default, `not_a_consumer` and `consumer_not_allowed`;
  - their own orders with dispatches, with no total through a dealer.
- `[FARM-002] Consent from the portal (contract)`: the portal channel, the first date kept, withdrawn.
- `[FARM-003] Rating from the portal (contract)`: once, then `rating_exists` and `not_found`, and an officer's rating without its comment.
- `[FARM-001] PortalHome`:
  - closed while off;
  - an installation rated;
  - consent given;
  - a complaint rated with an officer, with no Rate button.
- `[FARM-001] PortalShell and FarmersToPortal`: staff pointed back, and a farmer sent to `/portal`.

To check by hand in the mock:

1. As Admin, set **The farmers' portal** to On in Company settings and save.
2. Sign out, choose **Mobile number**, enter 6798273387 and code 123456.
3. Rate the installation, then choose **Yes, contact me**.
