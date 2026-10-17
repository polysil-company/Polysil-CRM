---
date: 2026-10-14
type: feature
title: Order list filters by area and office
dataIds:
  - SO-001
author: Nakul Srivastava
breaking: false
---

## Before

The orders list filtered by status, type, "Only my orders" and a search. The backend had added `territory_id` (up to 20, a state selecting its districts and talukas) and `owner_org_unit_id` (an office and the offices under it) to `GET /orders`, `/orders/stats` and `/orders/export` ("Five small changes" in `dealer-recruitment-and-small-changes.md`). The lead list already had an Area filter, but the orders list had neither.

## Now

- **Area** on the orders list.
  - **Picking:** states, districts or talukas, drilling down from the top, up to 20. Each area covers everything under it.
  - **The list:** the whole territory tree (`GET /lookups/territories?parent_id=`), with no counts. Orders have no "areas with orders" endpoint, and the lead list's counts would be of leads.
  - **The empty state** names the place: "Amreli has no talukas. Go back and choose Amreli itself."
- **Office**, for staff only (a dealer never sees it): one open office, by name.
  - A district office reads "Under Gujarat State".
  - Choosing an office covers the offices under it.
  - While the list loads, or if it fails, the pill says so.
- **Both filters:**
  - are kept in the URL (`area=`, `office=`), so a link to a filtered list works;
  - count in "Reset filters", which clears them;
  - go to **Download Excel** with the rest.
- The lead list's Area filter works as before, with its counts.
- Checked on a desktop in light mode and a phone in dark mode. axe found nothing with either popover open or with the list filtered.

## Discussion

- **One Area pill, two sources.** `LeadAreaFilter` takes `source: "leads" | "territories"`.
  - Both read one query, `areaRowsQueryOptions`, which gives the same rows either way.
  - The territories rows have their own cache key, so they never mix with the territory picker's search results.
  - `searchTerritories` gained an optional `parentId`.
- **Office is a single choice,** because the backend takes one `owner_org_unit_id`. The open offices fit in one list of 50 (`GET /org-units?is_open=true`, readable by anyone signed in).
- **`GET /orders/stats` isn't used yet.** It comes with the Accounts queue, plan item 3, and will take the same filters.
- **Plan §9's paragraph** gets its sentence once #124, which merges the duplicated paragraph, is in. This PR updates only the §9.1 row, to stay clear of that merge.
- **The mock:**
  - the list and the export share one filter;
  - an order is in an area when its territory, or any above it, is chosen;
  - an office covers the offices under it;
  - the mock export now honours the filters too, as the backend does.

## Files changed

- `src/features/orders/api/orders.schemas.ts`, `orders.api.ts`: `areas` and `officeId` on the list parameters, sent as `territory_id` and `owner_org_unit_id` on the list and the export.
- `src/features/orders/hooks/use-order-list-params.ts`: `area` and `office` in the URL, the filter count and reset.
- `src/features/orders/components/orders-toolbar.tsx`: the Area pill and the staff Office pill.
- `src/features/orders/api/orders.queries.ts`, `components/place-order.tsx`: no area or office on their fixed lists.
- `src/features/leads/components/lead-area-filter.tsx`, `src/features/leads/api/leads.queries.ts`: the `source` prop and `areaRowsQueryOptions`.
- `src/features/lookups/api/lookups.api.ts`, `lookups.schemas.ts`: `parent_id` on the territory search.
- `src/mocks/handlers/orders.ts`: area and office filtering, shared by the list and the export.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/orders/`: records and screens.

## Tests

- `src/features/orders/api/orders.test.ts`, `[SO-001] listOrders`:
  - Amreli's orders only;
  - two districts sent comma-joined;
  - the Amreli office gives the same orders;
  - the state office covers every district office.
- `src/features/orders/components/orders-ui.test.tsx`, `[SO-001] Sales orders list`:
  - states first, then Gujarat's districts;
  - picking Amreli narrows the table and the pill names it;
  - clearing it restores the list;
  - the Office pill narrows it, with "Reset filters" shown;
  - a dealer has no Office pill.
- The lead list's Area tests (`leads-ui.test.tsx`) pass unchanged.
- Walked through in the mock as a State Manager:
  - desktop light: the Area picker with Amreli chosen, and the filtered list;
  - phone dark: the Office picker, and the filtered list.
