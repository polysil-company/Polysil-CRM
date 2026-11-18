---
date: 2026-11-06
type: chore
title: The client's menu adds Org chart, Reports, Company settings and Tracking settings
dataIds:
  - APP-007
  - ADMN-008
  - RPT-002
  - ADMN-007
  - TRK-006
author: Nakul Srivastava
breaking: false
---

## Before

The client's site (`crm.polysilirrigation.com`) showed only the released screens in `RELEASED_NAV`. Org chart, Reports, Company settings and Tracking settings were built and on `integration`, but hidden from the client. Production's roles didn't hold the `reports` module either, so the reports would have answered 403 there.

## Now

- **The client's menu** (`RELEASED_NAV` in `backend/scripts/deploy_staging.py`) adds `org-chart`, `reports`, `company-settings` and `tracking-settings`.
- **The backend scope** (`RELEASED` in `backend/scripts/seed_prod.py`) adds `reports`, so the roles that hold reports in the permission matrix get them on production. Org chart needs no module; both settings screens use `masters` and the tracking screens use `tracking`, which were already released.
- **The live check** (`backend/live/inventory.json`): the ten report endpoints are no longer expected to answer 403 on production.
- Each screen still shows only to the roles whose permissions allow it.
- **Two tests that failed on a busy CI runner** now wait for the screen instead of reading it too early: the sign-in's **Send a new code** button (AUTH-001), which appears on the countdown's next tick, and the marketing order's dialog (MKT), which opens on "Loading…". `integration` was red on the first after #239 merged; this pull request's first run failed on the second.

## Discussion

- The client asked for these four screens on 6 Nov.
- The menu only appears on the client's site after the release steps: `deploy_staging.py --target prod deploy`, then `seed-prod` (it grants the new `reports` module), then `frontend-prod` (it rebuilds the menu).

## Files changed

- `../backend/scripts/deploy_staging.py`: four nav ids added to `RELEASED_NAV`.
- `../backend/scripts/seed_prod.py`: `reports` added to `RELEASED`.
- `../backend/live/inventory.json`: the report endpoints' `forbidden` lists emptied.
- `src/features/auth/components/mobile-sign-in.test.tsx`, `src/features/marketing/components/marketing.test.tsx`: wait for the button and the dialog's content.

## Tests

- `backend/tests/api/test_live_inventory.py`: "forbidden on production follows the release scope" passes with the new scope (the two tests that need a database weren't run here).
- `backend/tests/test_seed_prod_roles.py` and `tests/test_live_verify.py` pass.
- Both fixed test files passed three runs in a row locally.
- By hand, after the release: sign in on the client's site as an administrator and check that the four screens are in the menu and open.
