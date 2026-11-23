---
date: 2026-10-18
type: feature
title: Tracking settings and who looked
dataIds:
  - TRK-006
  - TRK-007
author: Nakul Srivastava
breaking: false
---

## Before

The tracking policy (how often a location is taken, working hours, how long history is kept, the photo rule, the consent text) could only be changed in the database. Nobody could see who had looked at whose location.

## Now

Built to `field-tracking-contract.md` §3 Admin and the generated `tracking.md`. This completes the web screens of item 35.

**Tracking settings** (`/tracking-settings`, Admin, `masters.view`)

- **Policy** tab: the policy in force and since when, in words.
  - "A location every 2 min, or every 50 m moved"
  - "09:00 to 19:00, monday to saturday"
  - "Location history kept: 90 days"
  - "Photo at check-out: Optional"
  - The consent version and its full text.
- **Save a new version** (for those with `masters.edit`):
  - It opens on a copy of the version in force, taking over at the start of tomorrow, India time. A version is never edited, and the form says so.
  - Fields: when it takes over, seconds between locations, the distance filter, the days kept, the working hours and days, the photo rule, and the consent version and text.
  - Each field is checked against the backend's bounds before sending: 15 to 3,600 seconds, 0 to 5,000 m and 7 to 3,650 days. The day must end after it starts, at least one day must be chosen, the version must be letters, digits, dots, dashes or underscores, and nothing may start in the past.
  - When the consent version changes, the form says everyone will be asked to agree again.
  - `policy_exists` lands on **Takes over**; other field refusals land on their fields.
- **Who looked** tab: "Hetal Shah looked at the route of Ravi Patel for Friday 16 October", "… the visits of …", "… the team map", newest first, with **Show more**.
  - **Whose location** narrows it to one person.
  - The backend shows it to Admin and the MD only. For anyone else the list is empty, and the empty state says so.
- The tab is in the URL.

**The mock**

- Policy versions are kept. The one in force is the latest that has started, and the check-in config, the consent asked and the photo rule all follow it.
- Saving refuses the same start, the past, out-of-range values and anyone without `masters.edit`.
- Reading the team map, someone else's route or someone else's visits adds a row to the view log. It starts with a few rows by the District Manager.

**Polish on screens from the last three PRs**

- A card without a header now has room above its content: the ratings list and summary, the portal's consent card, My visits and the view log.
- The policy cards use level-2 headings, which axe asked for.

Walked as Admin on a desktop in light mode and a 390 px phone in dark mode: the policy, a new version with a new consent version, and who looked. Axe found nothing once the headings were fixed, with no console errors and no sideways scroll.

## Discussion

- **Admin, under masters.** Saving needs `masters.edit` (the policy table's own row rule), so the page sits beside Company settings and is gated the same way.
- **A copy of the version in force.** Most saves change one or two figures, so the form starts from what is in force rather than from blanks.
- **The people filter comes from the log itself.** A list of the team would itself be a look at the team map and add a row to the log, so the filter uses the people already named in it.

## Files changed

- `src/features/tracking/api/policy.schemas.ts`, `.api.ts`, `.queries.ts`, `.mutations.ts`: new, the policy and the view log.
- `src/features/tracking/lib/policy-form.ts`: new, the draft, its checks, the request and the working days in words.
- `src/features/tracking/components/tracking-settings.tsx`: new, both tabs and the form.
- `src/app/(app)/tracking-settings/page.tsx`: new route; `src/components/layout/navigation.ts`: the Tracking settings item.
- Mock: `src/mocks/handlers/policy.ts` (new); `src/mocks/handlers/visits.ts` (the config, consent and photo rule from the policy in force), `src/mocks/handlers/tracking.ts` (logging), `src/mocks/db.ts`, `src/mocks/handlers/index.ts`.
- `src/features/ratings/components/ratings-page.tsx`, `src/features/portal/components/portal-home.tsx`, `src/features/tracking/components/my-visits.tsx`: room above headerless card content.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: TRK-006 and TRK-007.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/tracking/tracking-*`.

## Tests

`src/features/tracking/components/policy.test.tsx`, 7 tests:

- `[TRK-006] The new-version form's rules`:
  - it starts tomorrow from the version in force, and every field is checked;
  - the working days in words.
- `[TRK-006] Tracking policy (contract)`:
  - a version added, then `policy_exists`, the past and no `masters.edit` refused;
  - a new consent version asks again, with its text.
- `[TRK-007] View log (contract)`: the team map and a route logged, the filter by person, and empty for a District Manager.
- `[TRK-006] TrackingSettings`:
  - the policy in words, then a version saved after fixing a field;
  - who looked, filtered by person.

To check by hand in the mock as Admin:

1. Open Admin → **Tracking settings**.
2. Choose **Save a new version**, change the consent version, and save.
3. Open **Team map** and a route, then come back to **Who looked**.
