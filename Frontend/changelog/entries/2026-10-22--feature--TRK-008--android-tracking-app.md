---
date: 2026-10-22
type: feature
title: The Android app for field staff, with duty tracking
dataIds:
  - TRK-008
author: Nakul Srivastava
breaking: false
---

## Before

Field staff could check in to visits from a browser, and managers could see the team map and a day's route. But nothing recorded a route: a browser can't track location in the background (`field-tracking-contract.md`). The client wants field staff on their own Android phones to record the start, the end and the route of each duty, so the server can work out the kilometres.

## Now

- **`mobile/`, a new Capacitor 8.5.3 app** (`com.polysil.crm`):
  - **The shell** loads the live web app (`server.url`, https only, no cleartext, navigation limited to our host, an offline page). Screen and logic changes reach phones without a new APK.
  - **Our own Kotlin tracking plugin** uses only free, first-party pieces:
    - Play Services' Fused location;
    - a foreground service of type `location`, with a permanent "Tracking on duty" notification;
    - Room, which keeps every fix until the server counts or names it;
    - OkHttp for uploads (never the WebView, which Android slows in the background);
    - WorkManager as the backup when the network returns.

    A boot receiver resumes a duty still open after a restart.

  - **The upload rules** follow the contract and live in plain Kotlin:
    - oldest first, at most `max_batch_points` per batch;
    - the `Idempotency-Key` is the sha256 of the sorted point ids;
    - after `200`, every point sent is deleted;
    - `batch_too_large` is split into parts, each with a new key;
    - `bad_clock` is shown to the person;
    - `401` keeps the points and waits for a token; `403` stops;
    - a network error or `5xx` resends the same body under the same key;
    - after any other `4xx` the key is never used again;
    - `duty.ended_at` stops the duty and tells the screen.
- **Duty** (`/duty`), a Sales menu item shown only inside the app to staff who track:
  - **The consent first**, if this version isn't accepted yet.
  - **One card per missing step:** "Allow all the time", battery optimisation off, notifications on Android 13 and up, and GPS on. Each card has a button to its setting, and **Go on duty** stays off until every step is done.
  - **Autostart advice** for Xiaomi, Redmi, POCO, Oppo, Realme, Vivo, OnePlus and Samsung phones, linked to dontkillmyapp.com. It's advice, not a blocker.
  - **Go on duty:** one fresh fix, then `POST /tracking/duty/start`, then the tracker starts with **the id the server answered**.
  - **Go off duty:** the tracker sends what's waiting, then `POST /tracking/duty/end`, then the tracker stops.
  - **What it shows:** "On duty since 9:02", the last upload, the points waiting and today's km from the route.
  - **Every state:** loading; offline, said calmly; a wrong clock; a duty the server ended ("Duty ended after working hours"); an error. In a browser, Duty says it lives in the app.
- **The token hand-off:** `lib/auth/session-store.ts` passes each new access token to the tracker (`setAccessToken`), and an empty one on sign-out. It's a no-op in a browser. This is the one exception to "never pass tokens", written down in `AGENTS.md` §6.
- **`.github/workflows/android-apk.yml`:**
  - on a pull request that touches `mobile/`: lint, unit tests and a debug APK;
  - on demand: a signed `polysil-tracking-<version>.apk`, with the keystore from GitHub secrets.
- **`mobile/README.md`:** the install guide for staff (install from this source, Google's unverified-developer step, the permissions, autostart), and the developer notes.

## Discussion

- **Until BE-032 lands, the team map shows staff as stale while the app is closed.** BE-032 (a device token) is logged on the handoff's branch. Until then the tracker uploads with the web session's token, which lasts 15 minutes. After that, points wait on the phone; nothing is lost, since the server takes points up to its retention period, and they go up when the app is next opened. The native side never refreshes the token itself, because two refreshers would trip `refresh_reused`.
- **`server.url` in production:** Capacitor documents it as meant for live reload. We use it on purpose, as agreed, and keep it narrow: https only, no cleartext, our host only, an offline page.
- **Versions:**
  - Capacitor 8.5.3 (latest), whose template pins the Android Gradle Plugin at 8.13.0 with Gradle 8.14.3 and SDK 36. AGP 9.2 is newer, but Capacitor 8's own Android library is built on AGP 8, so the template's version stays.
  - Kotlin 2.4.21, KSP 2.3.12, Play Services Location 21.4.0, Room 2.8.4, WorkManager 2.11.2, OkHttp 5.3.2, kotlinx-serialization-json 1.12.0. All free and open source; no paid SDK.
- **Built, but not yet run as an Android build:** the build sandbox blocks `dl.google.com`, where the Android SDK and Google's Maven libraries are served. So `./gradlew lint test assembleDebug` couldn't run here; it runs in the new workflow. The upload rules' 15 unit tests did run here, as plain JVM tests with Kotlin 2.4.21.
- **Choices written down:**
  - The GPS interval is `interval_seconds`, with the distance filter, as the contract says.
  - A batch whose key a `4xx` used up is halved until the point at fault is alone, and that point is dropped, since the server will never take it.
  - The plugin adds `openSettings` (the app's settings or the location switch) and a phone maker field to `getDeviceId`, for the permission and autostart cards.
- **Still to do:**
  - the field pilot (3 to 4 phones of different brands, a full day each, compared with the real trip);
  - BE-032;
  - the production web URL for `CAP_SERVER_URL`;
  - the release keystore in GitHub secrets.

## Files changed

- `mobile/` (new):
  - `package.json`, `capacitor.config.ts`, `www/` (the start and offline pages);
  - `android/` (Capacitor's template, plus the manifest, the Gradle setup and signing from the environment);
  - `android/app/src/main/java/com/polysil/crm/tracking/` (the plugin, service, Room store, uploader, worker, boot receiver);
  - `tracking/core/` with its JVM tests;
  - `README.md`.
- `.github/workflows/android-apk.yml` (new).
- `src/lib/native/tracking-plugin.ts` (new): the plugin, registered once.
- `src/lib/auth/session-store.ts`: the token hand-off.
- `src/features/tracking/native/` (new): the Zod-checked bridge and `useIsNativeApp`.
- `src/features/tracking/api/duty.*` and `native.queries.ts` (new); `visits.schemas.ts` reads the intervals and the open duty.
- `src/features/tracking/components/duty-screen.tsx`, `lib/duty-labels.ts`, `hooks/use-browser-fix.ts` (one fix as a promise).
- `src/app/(app)/duty/page.tsx` (new); `src/components/layout/navigation.ts` and `use-nav-gates.ts`: Duty behind the `native-app` gate.
- `src/mocks/`: duty start and end, `/locations/batch`, and the open duty in the config.
- `package.json`: `@capacitor/core` 8.5.3.
- `AGENTS.md` §6: the token exception.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`, `Docs/Plan.md`, `Docs/Tested-Features.md`.

## Tests

- **Kotlin, as JVM unit tests** (`mobile/android/app/src/test/…/core/`, 15):
  - the batch key (sha256 of the sorted ids, whatever their order);
  - splitting at the batch limit, oldest first;
  - deleting every point sent after `200`, rejected ones too;
  - keeping points and resending the same body and key after a network error and a `5xx`;
  - keeping points on `401`, and sending nothing without a token;
  - stopping on `ended_at` and on `403`;
  - `batch_too_large` split under new keys;
  - `bad_clock` reported and its key never used again;
  - after another `4xx`, no key reused and the point at fault dropped;
  - the body and the answers read.
- **Vitest:**
  - `tracking-bridge.test.ts`: the bridge is a no-op in a browser.
  - `duty-labels.test.ts`: the blockers in order, upload problems, the server's end reasons, autostart by maker.
  - `duty.test.tsx`, through the API: consent needed, one open duty answered again, the end, `duty_not_found`.
  - `duty.test.tsx`, the screen:
    - in a browser;
    - the consent first;
    - Go on duty off until every step is done, one card each, with autostart advice;
    - on duty: the API first, then the tracker with the server's id;
    - off duty: flush, end, stop, in that order;
    - points waiting while offline;
    - the server ending the duty.
  - `session-store.test.ts`: each token handed to the tracker inside the app, an empty one on sign-out, never in a browser.
