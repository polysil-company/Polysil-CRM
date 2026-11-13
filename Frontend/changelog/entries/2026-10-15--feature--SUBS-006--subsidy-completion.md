---
date: 2026-10-15
type: feature
title: "Subsidy completion: the farmer's share, the dispatch date, the bells, Sprinkler steps"
dataIds:
  - SUBS-006
  - SUBS-002
  - NOTIF-001
  - SO-008
author: Nakul Srivastava
breaking: false
---

## Before

The backend added these, all additive (`subsidy-completion.md`):

1. A subsidised order's `payable` is the farmer's share: at most the total, less scheme benefits.
2. `dispatched_on` on a subsidy file: the first dispatch of a subsidised order naming its lead. Stage 7 takes it as the supply date when `supply` isn't sent.
3. Six bell kinds about a subsidy file (`resource.type: subsidy_application`).
4. Reopening a closed file.
5. Sprinkler areas between two table steps: the next step's quantities, a pro-rata unit cost, and an `area_between_steps` warning.

The frontend had none of these, except reopening (4), which PR #137 builds. The Sprinkler area was a list of the table's steps. The bell showed subsidy notices with the plain icon and no link.

## Now

- **The farmer's share (§1):**
  - the order schema reads `payable`;
  - a subsidised order's Subsidy card says "Payable ₹…: the farmer's share";
  - the mock works it out as the backend does: never below 0 or above the total.
- **The dispatch date (§2):**
  - a subsidy file shows **Dispatched on** beside the Reg. No., or "Not yet";
  - recording stage 7 says under the supply date "Dispatched on 12 Oct 2026. Left empty, the supply date is taken from it.";
  - the form already sent only changed fields, so an untouched supply date isn't sent and the backend fills it.
- **The bells (§3):** `subsidy_returned`, `subsidy_query`, `subsidy_tr_failed`, `subsidy_closed`, `subsidy_cancelled` and `subsidy_reopened` each have an icon. `subsidy_application` records open `/subsidy/{id}` and are named "Subsidy file".
- **Sprinkler steps (§5):**
  - the area is typed, like the other systems, and checked against the table's range ("Between 0.4 and 5 Ha.");
  - an area between two steps is calculated, with the warning in the handover's words: "The area is between table steps. Quantities use the next step; the unit cost is in between.";
  - a scheme needing an exact step still answers `exact_area_match_required` on the area.
- **The mock:**
  - `dispatched_on` comes from the first un-voided dispatch of a subsidised order naming the lead, and one seeded file short of stage 7 has one;
  - stage 7 fills `supply` from it when the key isn't sent;
  - Sprinkler takes 0.4 to 5 Ha, with the warning between steps.
- Checked on a desktop in light mode and a phone in dark mode: the file's Dispatched on, stage 7's hint, and a 1.3 Ha Sprinkler. axe found nothing. The bell and the payable line are checked by tests.

## Discussion

- **Not part of go-live** (the user, 13 Oct); plan item 18.
- **Stacked on #143** (#142, #141, #140 under it). Merge in order and retarget each to `integration` first.
- **Reopening a closed file (§4) is PR #137,** on its own branch.
- **The payable shows only on the Subsidy card.** The order page shows no payable or payments elsewhere yet: that is plan item 26 (payments).
- **Not yet checked on staging.**

## Files changed

- `src/features/orders/api/orders.schemas.ts`, `src/features/orders/components/order-subsidy.tsx`, `src/mocks/handlers/orders.ts`: `payable`, and the farmer's share on the card.
- `src/features/subsidy/api/subsidy-applications.schemas.ts`, `src/features/subsidy/components/application-detail.tsx`, `application-actions.tsx`, `src/mocks/handlers/subsidy-applications.ts`: `dispatched_on`, and the stage 7 hint and fill.
- `src/features/notifications/api/notifications.schemas.ts`, `src/features/notifications/components/notification-bell.tsx`, `src/lib/navigation/resource-href.ts`: the six kinds, and the file's link.
- `src/features/subsidy/components/calculator-inputs.tsx`, `src/features/subsidy/lib/calculator-draft.ts`, `src/features/subsidy/lib/subsidy-labels.ts`, `src/features/subsidy/components/calculator-results.tsx`, `src/mocks/handlers/subsidy.ts`: Sprinkler between steps.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/subsidy/{application-dispatched,stage7-supply-hint,sprinkler-between-steps}-*`: records and screens.

## Tests

- `src/features/subsidy/api/subsidy-applications.test.ts`: stage 7 takes the dispatch date as the supply date when none is sent.
- `src/features/subsidy/components/applications-ui.test.tsx`: the file shows Dispatched on, and stage 7 offers it.
- `src/features/notifications/components/notification-bell.test.tsx`: a subsidy bell opens its file.
- `src/features/orders/components/order-subsidy.test.tsx`: the payable is the farmer's share, at most the total, and the card says so.
- `src/features/subsidy/api/subsidy.test.ts`, `src/features/subsidy/lib/calculator-draft.test.ts`, `src/features/subsidy/components/subsidy-calculator.test.tsx`: Sprinkler takes an area between steps (with the warning in words) and refuses one outside the range. These three replace the tests that wanted a tabulated area.
- Walked through in the mock: desktop light and phone dark.
