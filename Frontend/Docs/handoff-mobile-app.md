# Handoff: the Android field tracking app (TRK-008)

**Prompt for the agent:** read this file, then `Frontend/AGENTS.md` and `backend/docs/handover/field-tracking-contract.md`. Build the app described here. Work on a branch from `integration`, and open PRs against `integration`.

Ask the user only if something here is blocking. For any other decision, make a reasonable choice and write it down in the PR.

## Rules for this work

- **Licences:** free and open-source only. **Don't** use Transistorsoft or any paid SDK; the user has ruled out paid licences.
- **Before installing anything:** look up the current docs and pick the latest stable versions. That covers Capacitor, Android Gradle Plugin, Kotlin, Play Services Location, Room and OkHttp.
- **Secrets:** never commit a keystore, password or token.
- **Release menu:** don't touch `RELEASED_NAV` in `backend/scripts/deploy_staging.py`.
- **Real people:** no messages to real customers.
- **Backend:** don't invent backend rules. If something is missing, add a `BE-NNN` entry to `docs/Backend-Tasks.md`. **BE-032** (the device token) is already logged.
- **Web code:** follow `Frontend/AGENTS.md`:
  - strict TypeScript, with no `any` and no `as`;
  - explicit return types;
  - Zod at the API boundary;
  - Tailwind tokens only;
  - records, Data-IDs and a changelog entry;
  - `npm run verify` and `npx prettier --check .` must pass.
- **Kotlin code:**
  - Kotlin only, with null-safety and no `!!`;
  - unit tests for the batching and retry logic;
  - `./gradlew lint test assembleDebug` must pass.

## What the client wants

Field staff use their **own Android phones**. While on duty, the app records:
- the **start** time and place;
- the **end** time and place;
- the **route**, from which the server works out **km**.

**Not wanted:**
- live tracking (batches every couple of minutes are fine);
- selfies (the visit photo is optional and set by the admin);
- iOS for now.

The app is given out as an **APK**, not through the Play Store.

## The approach the user agreed

**Capacitor shell plus our own Kotlin tracking module.**

- **The shell:** Capacitor loads the live web app.
  - The Next.js app can't be bundled as static files (`src/proxy.ts`, dynamic routes). Use Capacitor's `server.url`, taken from build config, with a separate value for staging and production.
  - Check Capacitor's current docs on `server.url` in production. Keep cleartext off, and limit `allowNavigation` to our own host.
  - Screen and logic changes then reach phones without a new APK.
- **The tracking module:** our own small Capacitor plugin in Kotlin, using only Google's free, first-party building blocks:
  - `FusedLocationProviderClient` (Play Services Location) for GPS fixes;
  - a **foreground service** of type `location`, with a permanent "Tracking on duty" notification;
  - **Room** (SQLite) to keep every point on the phone until the server confirms it;
  - **OkHttp** for native uploads. Never upload from the WebView: Android slows WebView requests after about 5 minutes in the background.
  - **WorkManager** only as the backup for retrying uploads once the network returns.
- **Shared with the web app, already built and merged:** visits, team map, route of a day, tracking settings and the view log, under `Frontend/src/features/tracking/*`.
  - Visit check-in already uses the browser's location (`hooks/use-browser-fix.ts`). Inside the WebView this works once Android grants location.

## Layout

| Path | What |
|---|---|
| `mobile/` (new, at repo root) | Capacitor project: `capacitor.config.ts`, `android/`, its own `package.json` and README |
| `mobile/android/app/src/main/java/…/tracking/` | the Kotlin plugin: service, location client, Room DAO, uploader, permissions |
| `Frontend/src/features/tracking/native/` | the typed bridge (`registerPlugin`), Zod-checked results, a no-op on the web |
| `Frontend/src/app/(app)/duty/` | the Duty screen, shown only inside the app (`Capacitor.isNativePlatform()`) |
| `.github/workflows/android-apk.yml` | builds a signed APK on demand, with the keystore from GitHub secrets, and attaches it as a workflow artifact |

## The plugin's interface (TypeScript side)

```ts
interface TrackingPlugin {
  getDeviceId(): Promise<{ deviceId: string }>; // uuid made on first run, kept in app storage
  checkPermissions(): Promise<TrackingPermissions>;
  requestPermissions(): Promise<TrackingPermissions>; // fine location, then "all the time", notifications (13+)
  openBatterySettings(): Promise<void>; // ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
  setAccessToken(o: { token: string; expiresAt: string }): Promise<void>; // the web app calls this after each sign-in or refresh
  start(o: StartOptions): Promise<void>; // dutyId, intervalSeconds, distanceFilterM, maxBatchPoints, apiBaseUrl
  stop(): Promise<void>;
  flush(): Promise<FlushResult>; // upload now: { accepted, duplicates, rejected, pending }
  getStatus(): Promise<TrackingStatus>; // onDuty, dutyId, since, lastUploadAt, pendingPoints, lastError
  addListener(e: "status" | "serverEndedDuty", fn: (s: TrackingStatus) => void): Promise<PluginListenerHandle>;
}
// TrackingPermissions: { location: "granted" | "denied" | "prompt"; background: …; notifications: …; batteryUnrestricted: boolean }
```

## The duty flow (follow section 1 of `field-tracking-contract.md` exactly)

1. **When the app opens:**
   - call `GET /me/tracking-config`;
   - if `tracking_allowed` is false, hide Duty;
   - if consent is out of date, show the consent screen and call `POST /tracking/consent`. `acceptTrackingConsent` in `visits.api.ts` already exists.
2. **Before duty can start**, the Duty screen requires:
   - location set to **"Allow all the time"**;
   - **battery optimisation off**;
   - notifications allowed on Android 13 and later;
   - GPS switched on.

   Each missing item shows one plain-language card with a button that opens the right setting. Start stays disabled until all of them are done.
   - Add an **"Allow autostart"** help card for the brand from `Build.MANUFACTURER` (Xiaomi, Redmi, POCO, Oppo, Realme, Vivo, OnePlus, Samsung), linking to that brand's page on dontkillmyapp.com.
   - This card is advice, not a blocker: the app can't check the setting.
3. **Start:**
   - the **web side** calls `POST /tracking/duty/start` with a uuid made on the phone, `device_id`, `at`, `sent_at`, and lat/lng from one fresh fix;
   - then call `start()` with **the id from the answer** and the config's `interval_seconds`, `distance_filter_m` and `max_batch_points`.
4. **The service:**
   - stores every fix in Room, with a new uuid and the duty id;
   - fields: `recorded_at`, lat, lng, `accuracy_m`, `speed_mps`, `heading`, `altitude_m`, `battery_pct`, and `is_mock` (from `Location.isMock` / `isFromMockProvider`).
5. **Upload:**
   - every `interval_seconds`, and when the network returns, call `POST /locations/batch`;
   - send points oldest first, at most `max_batch_points` at a time, with `device_id` and `sent_at`;
   - `Idempotency-Key` is the **sha256 of the sorted point ids**.
6. **Handling the answer:**

   | Answer | What to do |
   |---|---|
   | `200` | Delete every point sent (counted or named). Rejected points are never accepted later. If `duty.ended_at` is set: stop, update the status, and emit `serverEndedDuty` |
   | `422 batch_too_large` | Split; each part gets a new key |
   | `422 bad_clock` | Show the user that the phone's clock is wrong |
   | `401` | Keep the points; wait for a new token |
   | `403` | Stop; this role doesn't track |
   | Other `4xx` | **Never** retry under the same key |
   | Network error or `5xx` | Retry the same body with the same key, with backoff |

7. **End:**
   - `flush()`;
   - then the web side calls `POST /tracking/duty/end` with the fix and `sent_at`;
   - then `stop()`.
8. **Reboot:** a `BOOT_COMPLETED` receiver restarts the service if a duty is still open. Android allows this only with background location, which step 2 requires.

## Sign-in in the background: BE-032

- **The problem:** the web app's access token lives only in memory and lasts 15 minutes. The refresh cookie rotates, so the native code **must not** refresh it itself: two refreshers trigger `refresh_reused`, which signs the person out everywhere.
- **Until BE-032 lands:**
  - the web app passes each new access token to the native code with `setAccessToken`.
    - `AGENTS.md` §6 says no code outside the API client reads or passes tokens. Make this hand-off **only inside `src/lib/auth/session-store.ts`**, as a no-op on the web.
    - Note the exception in `AGENTS.md` in the same PR, as its first rule requires;
  - the native code uploads while that token is valid;
  - otherwise it keeps the points (`401`, so it waits).
  - The server accepts points up to the retention period old (90 days), so nothing is lost. Uploads catch up whenever the app is opened.
  - **Say this plainly in the PR:** until BE-032 lands, the team map shows staff as stale while the app is closed.
- **When BE-032 lands:** request the device token at duty start, keep it in `EncryptedSharedPreferences`, and use it for batches and duty end.

## Screens

- **Duty** (app only):
  - a large on/off toggle;
  - "On duty since 9:02";
  - last upload time;
  - points waiting;
  - today's km, from `GET /tracking/users/{me}/route?date=`;
  - the permission cards from step 2.
- **States to cover:**
  - loading;
  - offline (points waiting, shown without alarm);
  - permission missing;
  - the server ended the duty ("Duty ended after working hours");
  - error.
- **Layout:** mobile-first, with 44 px touch targets, labelled and reachable by keyboard.
- **Menu:** add a "Duty" item for tracking staff, shown only inside the app.
- **Elsewhere:** the existing Visits screens are used inside the app unchanged.

## Building and giving out the APK

- **Signing:**
  - `./gradlew assembleRelease`, signed with a release keystore;
  - the keystore and its passwords live **only** in GitHub secrets and the owner's password manager;
  - the workflow produces `polysil-tracking-<version>.apk`.
- **`mobile/README.md`:** a one-page install guide for staff covering:
  - allow install from this source;
  - Google's one-time "unverified developer" flow, which reaches India in 2027: a restart and a 24-hour wait, unless the company registers as a developer;
  - the permissions;
  - autostart.
- **Versions:** bump `versionCode` and `versionName` on every release. Changes only to the web app need no new APK.

## Tests and checks

- **Kotlin unit tests:**
  - the batch key (sha256 of sorted ids);
  - splitting at `max_batch_points`;
  - deleting points after `200`;
  - keeping points on network errors and `401`;
  - stopping on `ended_at` and on `403`;
  - not reusing a key after a `4xx`.
- **Vitest:**
  - the bridge is a no-op on the web;
  - the Duty screen's states;
  - Start disabled until permissions are granted;
  - the start and end order (API call, then plugin call).
- **Records:** add Data-ID **TRK-008** to the registry and `Docs/Data-IDs.md`, plus a changelog entry, `Docs/Plan.md` and `Docs/Tested-Features.md`.
- **Field pilot before rollout:** 3 to 4 staff phones of different brands (include a Xiaomi or Redmi and a Vivo or Oppo), one full working day each, screen off in a pocket. Compare the km on the route page with the real trip, and record any gaps.

## Done when

- A debug APK installs on an Android phone, signs in, and shows Duty to tracking staff only.
- With the screen off, points upload every interval while the app is open in the background. When the app is closed they upload on next open, and continuously once BE-032 is in.
- Duty start and end appear on the route page with the correct km.
- CI builds a signed APK on demand.
- Tests are green, and the PR lists what still waits on BE-032 and the pilot.
