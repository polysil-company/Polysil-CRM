# Field tracking: the contract for the Android app and the map screens

> **Status: built on the backend** (migration 030). These shapes are what the API returns. They only gain fields from here.

The client wants field tracking at launch: visit check-in and check-out with GPS and a photo, background tracking with route history, a manager's team map, and staff consent.

**Your part:**
- a Capacitor Android wrapper of the web app, with `@capacitor-community/background-geolocation`;
- the app screens (consent, duty toggle, visits);
- the web screens (team map, route of a day, admin settings), with Leaflet and OpenStreetMap tiles.

A PWA cannot track in the background, so only the app sends background points. Visit check-in and check-out also work from the web app.

All paths are under `/api/v1`. Coordinates are JSON numbers in degrees. Times are ISO 8601 with an offset.

---

## 1. The app's sequence

1. `GET /me/tracking-config` at start, and after every duty start.
2. If `consent.accepted_version` differs from `consent.required_version`: show the consent screen, then `POST /tracking/consent`.
3. Start duty: `POST /tracking/duty/start` with an id the phone generates. **Use the id in the answer**, which may differ from yours (a reinstall mid-duty gets the open session back).
4. Configure the plugin with `interval_seconds` and `distance_filter_m`. Store every fix locally with a new uuid.
5. Every `interval_seconds`, or on reconnect: `POST /locations/batch`, oldest first, at most `max_batch_points` per batch.
6. Delete a stored point only after a batch answer counts it or names it.
7. When a batch answer's `duty.ended_at` is set, stop tracking and flip the toggle off. The server ended the duty: idle after hours, or consent withdrawn.
8. End duty: `POST /tracking/duty/end`.

Ask Android for "Allow all the time" location and to ignore battery optimisation when duty starts. Say why in plain words; staff switch tracking off when it drains the battery.

## 2. Idempotency: one key per distinct payload

Every POST takes `Idempotency-Key`. The server stores the first answer to a key, **4xx included**, and replays it. A different body under a used key is `409 idempotency_conflict`.

- **A new key for every distinct payload.** For a batch: the sha256 of its sorted point ids. A batch with extra points is a new payload and gets a new key.
- **Never retry a 4xx under the same key.** Fix the cause (split the batch, accept consent, close the open visit), then send with a new key.
- On a network failure or a 5xx: retry the same body with the same key.

## 3. Endpoints

### `GET /me/tracking-config`

```json
{ "data": {
    "tracking_allowed": true,
    "consent": { "required_version": "v1", "accepted_version": null, "text": "..." },
    "interval_seconds": 120,
    "distance_filter_m": 50,
    "working_hours": { "start": "09:00", "end": "19:00", "days": [1,2,3,4,5,6], "timezone": "Asia/Kolkata" },
    "max_batch_points": 500,
    "visit_photo_required": false,
    "on_duty": null } }
```

`tracking_allowed: false`: the user's role does not track (functional roles, dealers). Hide the duty toggle. `days` are ISO weekdays, 1 for Monday.

### `POST /tracking/consent`

```json
{ "version": "v1", "accepted": true }
```

`accepted: false` withdraws consent and ends any open duty.

### `POST /tracking/duty/start` and `/tracking/duty/end`

```json
{ "id": "uuid", "device_id": "app install id", "at": "2026-10-05T09:02:11+05:30",
  "lat": 23.0225, "lng": 72.5714, "accuracy_m": 12 }
```

```json
{ "data": { "id": "uuid", "started_at": "...", "ended_at": null, "end_reason": null, "outside_hours": false } }
```

- Start answers `201`, or `200` with the session already open.
- End takes `{ "id", "at", "lat", "lng", "accuracy_m" }` and answers `200`. Ending an ended session answers `200` unchanged.
- **Send `sent_at` (the phone's clock when sending) on duty start and end, check-in and check-out too.** A phone clock more than 5 minutes off is then corrected, as on batches. Without it, a time in the future is taken as now.
- `409 consent_required` on start without consent. `404 duty_not_found` on end with an id that is not yours.
- `end_reason`: `user`, `auto`, `consent_withdrawn` or `deactivated`.

### `POST /locations/batch`

```json
{ "device_id": "...", "sent_at": "2026-10-05T11:30:00+05:30",
  "points": [
    { "id": "uuid", "duty_id": "uuid", "recorded_at": "2026-10-05T09:04:11+05:30",
      "lat": 23.0230, "lng": 72.5720, "accuracy_m": 9, "speed_mps": 4.2, "heading": 181,
      "altitude_m": 52, "battery_pct": 71, "is_mock": false } ] }
```

```json
{ "data": { "accepted": 497, "duplicates": 2,
            "rejected": [ { "id": "uuid", "reason": "off_duty" } ],
            "duty": { "id": "uuid", "ended_at": null, "end_reason": null } } }
```

- `sent_at` is the phone's clock at sending. The server corrects a phone clock that is off; `422 bad_clock` only when it is off by more than a day.
- A duty the server ended on idleness still takes the phone's points up to 14 hours after its start, so an evening without signal is not lost.
- Map the plugin's `simulated` to `is_mock`. Optional fields may be omitted.
- Rejection reasons: `off_duty`, `future`, `too_old`, `bad_coordinates`, `unknown_duty`, `id_in_use`, `consent_withdrawn`. A rejected point is never accepted later; delete it.
- `422 batch_too_large` over `max_batch_points`. Split, one new key per part.

### Visits

**Check in:** `POST /visits`

```json
{ "id": "uuid", "lead_id": "uuid", "partner_id": null, "task_id": null, "place_name": null,
  "at": "...", "lat": 23.02, "lng": 72.57, "accuracy_m": 8 }
```

- Give a lead, or a dealer, or a `place_name`. A task is optional.
- `409 visit_open` when another visit is open. `error.fields.visit_id` names it; offer to open it.

**Check out:** `POST /visits/{id}/check-out`

```json
{ "at": "...", "lat": 23.02, "lng": 72.57, "accuracy_m": 10, "outcome": "met", "note": "Wants a quote for 2 acres" }
```

- `outcome`: `met`, `not_available`, `follow_up` or `other`.
- `409 photo_required` when the admin requires a photo and there is none. `409 visit_closed` when the visit is already closed.

**Photo:** `POST /visits/{id}/photos`, multipart, field `file`.
- JPEG, PNG, WebP or HEIC, up to 10 MB, up to 3 per visit.
- Accepted until 24 hours after check-in, so an offline photo still lands.
- `409 photo_limit`, `409 photo_window_closed`.

**List:** `GET /visits?user_id=&date=YYYY-MM-DD&lead_id=&limit=&cursor=`

```json
{ "data": [ { "id": "uuid", "user": { "id": "uuid", "full_name": "Ravi Patel" },
              "lead": { "id": "uuid", "label": "POL/GJ/2026-27/00079" }, "partner": null, "task_id": null,
              "place_name": null, "checkin_at": "...", "checkin": { "lat": 23.02, "lng": 72.57, "accuracy_m": 8 },
              "checkout_at": "...", "checkout": { "lat": 23.02, "lng": 72.57, "accuracy_m": 10 },
              "duration_minutes": 34, "outcome": "met", "note": "...",
              "auto_closed": false, "photo_count": 1 } ],
  "meta": { "next_cursor": null } }
```

- An open visit closes by itself after 12 hours (`auto_closed: true`).
- `GET /visits/{id}/photos/{photo_id}`: a ten-minute link, like complaint attachments.
- The lead's timeline shows `visit.checked_in` and `visit.checked_out`.

### Team map: `GET /tracking/team/latest`

```json
{ "data": [ { "user": { "id": "uuid", "full_name": "Ravi Patel", "role": "field_officer" },
              "on_duty": true, "last_seen_at": "...", "lat": 23.02, "lng": 72.57, "accuracy_m": 9,
              "battery_pct": 64, "is_mock": false, "stale": false,
              "open_visit": { "id": "uuid", "label": "POL/GJ/2026-27/00079", "since": "..." } } ] }
```

- Everyone the user may track. Off duty: `lat` and `lng` are `null`.
- `stale`: on duty, but silent for 15 minutes. Grey the marker.
- `is_mock`: the phone reported a fake location. Mark it.
- Poll every 60 seconds at most.

### Route of a day: `GET /tracking/users/{user_id}/route?date=YYYY-MM-DD`

```json
{ "data": {
    "user": { "id": "uuid", "full_name": "Ravi Patel" }, "date": "2026-10-05",
    "duty": [ { "id": "uuid", "started_at": "...", "ended_at": "...", "end_reason": "user" } ],
    "points": [ { "at": "...", "lat": 23.02, "lng": 72.57, "accuracy_m": 9, "is_mock": false } ],
    "stops": [ { "from": "...", "to": "...", "minutes": 22, "lat": 23.03, "lng": 72.58, "visit_id": "uuid" } ],
    "visits": [],
    "distance_km": "48.3", "point_count": 4210, "dropped_points": 4, "mock_points": 0 } }
```

- `date` is an Indian calendar day. `points` are oldest first, at most 2,000 for drawing; `point_count` is the raw count.
- `dropped_points`: fixes left out for poor accuracy or impossible jumps. Show "4 points left out".
- A stop is 10 minutes or more in one place. `visit_id` links a stop to its visit.
- `404` for a person outside the user's team.

### Admin

- `GET /tracking/policy`, `PUT /tracking/policy` (admin): the figures above, plus `retention_days`, `consent_version` and `consent_text`, and `effective_from` on `PUT`. A save adds a version; it never edits one.
- `GET /tracking/view-log?subject_user_id=&limit=&cursor=` (admin, MD): who looked at whose route, visits or the team map, and when.

## 4. Who sees what

| Role | Tracks self | Sees |
|---|---|---|
| Field officer | yes | own route and visits |
| District, state, regional manager | yes | their team (their office and below) |
| Admin, MD | yes | everyone; the view log |
| Accounts, dispatch, QC, support, marketing, the board | no | nothing |
| Dealers | no | nothing; visits do not appear on a dealer's view of the lead timeline |

`403` means the role has no tracking. An empty team map means nobody is in the user's team.

## 5. Screens

| Screen | Where | Notes |
|---|---|---|
| Consent | app, first run | the policy text; Accept or Not now. Ask again at the next duty start when the version changes |
| Duty toggle | app home | on or off, since when, last upload, points waiting |
| Visit check-in | app and web | lead or dealer picker, or a place name; the GPS fix and its accuracy. Warn above 100 m |
| Open visit | app and web | time since check-in, photos; Add photo, Check out |
| My visits | app | today's visits |
| Team map | web | markers by state: on duty, stale, off duty; battery; open visit. Click: today's route |
| Route of a day | web | path, stops, visits, duty spans, distance, date picker |
| Tracking settings | web, admin | the policy in force; save a new version |
| Tracking views | web, admin | the view log, filtered by person |

## 6. Defaults the client has not confirmed

These are admin settings, so a change needs no app release:
- tracking runs continuously on duty, Monday to Saturday, 9 am to 7 pm;
- a duty left on ends itself after the working day once the phone goes quiet for 30 minutes;
- the visit photo is optional;
- location history is kept 90 days;
- the consent text is a placeholder until HR sends theirs.
