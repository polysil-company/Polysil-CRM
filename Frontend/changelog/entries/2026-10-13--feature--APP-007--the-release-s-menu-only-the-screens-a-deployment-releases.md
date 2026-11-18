---
date: 2026-10-13
type: feature
title: "The release's menu: only the screens a deployment releases"
dataIds:
  - APP-007
author: Nakul Srivastava
breaking: false
---

## Before

The client's box releases the go-live scope in two places:

- the backend grants only those modules' permissions (`backend/scripts/seed_prod.py`);
- the deploy script builds the frontend with `NEXT_PUBLIC_NAV_ONLY`, the go-live menu (`RELEASED_NAV` in `backend/scripts/deploy_staging.py`).

Nothing in the frontend read `NEXT_PUBLIC_NAV_ONLY`, so the menu followed permissions alone. Screens whose module was released for another reason still showed. QR codes rides on `leads`; Subsidy masters and Masters ride on `masters`, which is released for offices and territories.

## Now

- **The variable.** `NEXT_PUBLIC_NAV_ONLY` (build time) is read and checked as a list of nav item ids, for example `dashboard,leads,quotations`. A badly formed value fails the build.
- **Outside the list,** a screen is gone from the sidebar and the command menu. Typing its address shows "You don't have access to this page", for every role, administrators included. Pages under a released item stay open, such as `/products/price-lists/…` under Products.
- **Inside the list,** permissions decide as before.
- **Unset or empty,** nothing changes: every screen the permissions allow shows. That covers local development, feature previews and the team's own staging box.

## Discussion

- **One rule, in one place.** The list is checked in `canSeeNavItem`, which the sidebar, the command menu, the header and the route guard (APP-006) all use. Something left out of the menu can't be reached by address either.
- **Hiding is a courtesy.** The backend's permission rows are still what enforces the scope.
- **A test reads the deploy script.** It checks that every id in `RELEASED_NAV` exists in the menu, so a renamed nav item can't silently hide a released screen.
- **Widening the release** takes both changes: a new `RELEASED_NAV` and a frontend rebuild, plus the backend's `seed_prod.py --modules …` for the permissions.

## Files changed

- `src/lib/env/client.ts` and its test: `NEXT_PUBLIC_NAV_ONLY` becomes `navOnly`.
- `src/components/layout/navigation.ts`: `isReleased`. `canSeeNavItem`, `visibleNavSections` and `canOpenPath` take the release list, defaulting to the build's.
- `src/components/layout/navigation.test.ts`: the release's tests.
- `.env.example`, `Docs/Environments.md`: the variable.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: APP-007.
- `Docs/Tested-Features.md`: the story.

## Tests

- **`src/components/layout/navigation.test.ts`, `[APP-007] the release's menu`:**
  - only released screens show for an administrator;
  - permissions still apply inside the release;
  - `/qr-codes` and `/subsidy-masters` are refused by address, while a page under a released item and a page outside the menu open;
  - no list releases everything;
  - every id the deploy script releases exists.
- **`src/lib/env/client.test.ts`:** the list is parsed, empty means everything, and a malformed list is refused.
