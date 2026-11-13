---
date: 2026-10-18
type: feature
title: The team map and a day's route
dataIds:
  - TRK-001
  - TRK-002
author: Nakul Srivastava
breaking: false
---

## Before

A manager couldn't see where the field team was, or where anyone had been on a given day.

## Now

Built to `field-tracking-contract.md` and the generated `tracking.md` (migration 030). This is the first web part of field tracking; the Android app that sends the locations is separate. Field tracking gets a new Data ID domain, `TRK`, and the `tracking` permission module.

**Team map** (`/team-map`, TRK-001)

- A **Team map** item under Sales for staff who hold `tracking.view`.
- Each person the user may track is listed in words beside the map:
  - **On duty**, **Not heard from** (silent for 15 minutes), or **Off duty**;
  - their role, when they were last seen, and their battery, with "Battery low: tracking stops if the phone dies" under 20 %;
  - an open visit ("On a visit to POL/… since 26 minutes ago");
  - **Fake location** when the phone reported one.
- On the map, people on duty are green dots, silent ones grey, and a faked location is a red ring. A key explains this, and colour is never the only signal.
- It refreshes every minute, the most the contract allows, and says so.
- A person, or their marker, opens their route.
- A field officer sees only themselves. A role without tracking is told so.

**Route of a day** (`/team-map/{person}?date=`, TRK-002)

- The day is in the URL, today by default. **The day before**, a date field and **The day after** move between days; the day after stops at today.
- It shows the distance, the time on duty, and the number of stops and visits.
- It counts the points recorded and says how many were left out for poor accuracy or impossible jumps. A day with faked points says so in red.
- The map draws the path, with stops (small grey), visits (large green), the start and the last point.
- **Duty** lists each span and why it ended.
- **Visits and stops** gives each stop's times and length. A visit names its lead (linked), the outcome, the time spent, its photos, its note, and whether it closed by itself after 12 hours.
- A day with nothing tracked says so. Someone outside the team opens the not-found page.

**A new pattern**

- `MapView` draws on Leaflet 1.9.4 (BSD-2) over OpenStreetMap tiles, credited on the map. It needs no API key and no marker images: markers are SVG circles coloured with token classes, and a path is a stroke only.
- It fits itself to what it shows and opens on Gujarat when empty.
- In dark mode the tiles are toned down.
- If Leaflet fails to load, it says everything is listed beside it.
- It has a story.

**Mock**

- Six people around Saurashtra: on duty, silent, off duty, one faked location, one on a visit.
- A repeatable day for each person: a drive through three villages and back, with stops, two visits on real mock leads, and seven points left out.
- `tracking.view` by scope: a field officer sees themselves, managers and Admin the team, other roles 403.

Walked as Admin on a desktop in light mode and a 390 px phone in dark mode. Axe found nothing and there was no sideways scroll. The sandbox's network blocks OpenStreetMap, so the screenshots show the markers and path on a blank map, and the console lists the failed tile requests. The tiles need a look on staging.

## Discussion

- **Leaflet with OpenStreetMap, as the contract asks.** Leaflet is about 40 KB, with no key and no lock-in. MapLibre needs a vector style server, and OpenLayers is heavier. React-leaflet isn't needed: one small effect drives the map.
- **The tiles in production.** OpenStreetMap's own tile servers suit light use only. Heavy use needs a provider or our own tile server; only `TILE_URL` in `map-view.tsx` changes (`TODO(TRK-001)`).
- **The lockfile.** The repo asks for Node 24 and npm 11; this sandbox has Node 22. The lockfile change is exactly the three new packages (`leaflet`, `@types/leaflet`, `@types/geojson`), checked with npm 11's `npm ci`.
- **This is part 35a.** Visit check-in and check-out on the web (35b), and the tracking settings and view log (35c), follow.

## Files changed

- `package.json`, `package-lock.json`: `leaflet` 1.9.4 and `@types/leaflet` 1.9.22, exact.
- `src/components/patterns/map-view.tsx`, `.stories.tsx`: new.
- `src/features/tracking/`: new.
  - `api/tracking.schemas.ts`, `.api.ts`, `.queries.ts`: the team, the route and the visit shape.
  - `lib/tracking-labels.ts`.
  - `components/team-map.tsx`, `components/route-day.tsx`.
- `src/app/(app)/team-map/page.tsx`, `src/app/(app)/team-map/[userId]/page.tsx`: new routes; `src/components/layout/navigation.ts`: the Team map item.
- `src/lib/auth/permissions.ts`: the `tracking` module; `src/mocks/data/permissions.ts`: its grants.
- Mock: `src/mocks/data/tracking.ts`, `src/mocks/handlers/tracking.ts` (new), `src/mocks/handlers/index.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: the `TRK` domain, TRK-001 and TRK-002.
- Records: `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/plan-13oct-2026.md`, `Docs/screenshots/tracking/`.

## Tests

`src/features/tracking/components/tracking.test.tsx`, 7 tests:

- `[TRK-001] Team map (contract)`: a manager sees the team, a field officer themselves, a QA manager gets 403.
- `[TRK-002] Route of a day (contract)`:
  - a past day with points in order, stops, visits, distance and points left out, and nothing for a day ahead;
  - 404 outside the team.
- `[TRK-001] TeamMap`:
  - every state, the battery warning, an open visit and a fake location in words, and the route link;
  - no tracking for the role.
- `[TRK-002] RouteDay`:
  - figures, visits with lead links, and the day before;
  - no duty, and no day after today.

To check by hand in the mock as Admin:

1. Open Sales → **Team map**.
2. Open Ravi Patel, then **The day before**.
