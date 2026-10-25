---
date: 2026-10-25
type: feature
title: The phone's own token for route uploads
dataIds:
  - TRK-009
  - TRK-008
author: Nakul Srivastava
breaking: false
---

## Before

The Android app's tracker uploaded the route with the web session's access token. `session-store.ts` handed it over after each sign-in and refresh. That token lasts 15 minutes and lives only while the screens are open. Once the app was closed, points waited on the phone until it was opened again, and the team map showed field staff as stale all day. It was also the one place a session token left the API client.

## Now

- **The phone's own token (BE-032, backend #206).**
  - After **Go on duty**, and on every launch of the app while a duty is open, the screens call `POST /tracking/device-token` with the phone's device id.
  - The answer goes to the native tracker (`setDeviceToken`), which uploads with it while the app is closed.
  - The token is good only for location batches, duty end and the tracking config. It lasts 30 days, and only while the sign-in it came from lives.
- **One call at a time.** Callers that arrive together share one call, so the tracker only gets the newest answer. Each call uses a new key, since the server never replays a token.
- **Kept safe on the phone.** `DeviceTokenStore.kt` seals the token with AES-GCM under a key kept in the Android Keystore.
- **When the server refuses it** (`401`, or any `403`), the tracker forgets the token and keeps every point. The batch in flight keeps its key, since the server refused it before recording the key. Points go up once the next launch hands over a new token. Before, a `403` used up the key, so its points could later be dropped.
- **The session token stays home.** `setAccessToken` and its hand-off in `session-store.ts` are gone, and so is the exception in `AGENTS.md` §6. The new exception there names the device token.
- **The duty stays on without a token.** If no token can be had when going on duty, the duty stays on. The points wait on the phone, and the Duty screen says so calmly.
- **Records:** BE-031 to BE-038 are ticked in `docs/Backend-Tasks.md`, with the backend's notes from #206.

## Discussion

- **Storage.** The backend suggested `EncryptedSharedPreferences`. androidx.security has deprecated it, and its reference points to the Android Keystore with `KeyGenerator` instead. That is what `DeviceTokenStore.kt` does, with no extra library. A backup restored onto another phone carries the sealed text but not the key, so it reads as no token, and the next launch asks again.
- **Where the launch call lives.** `DeviceTokenOnLaunch` sits in `AppShell`, so it runs on every signed-in page, not only on Duty. It renders nothing, and does nothing in a browser or while off duty.
- **Expiry format.** The expiry goes to the phone as `toISOString()`. Android's `SimpleDateFormat` misreads the server's microseconds.
- **Known limits.**
  - One person per phone (client question 9.5). If two people share a phone, points left from the first one's duty go with the second one's token, and the server refuses them.
  - The tracker's own `GET /me/tracking-config` and duty end still go through the screens, which is enough for now.
- **Before the APK:** the backend needs migrations 078 to 080 on each box (on the client's through #207 and its deploy). Until then, `POST /tracking/device-token` answers 404, and points wait on the phone as before.

## Files changed

- `src/features/tracking/api/duty.schemas.ts`, `duty.api.ts`: `deviceTokenSchema` and `issueDeviceToken` (`sensitive`).
- `src/features/tracking/native/device-token.ts` (new): `renewDeviceToken`, one call at a time.
- `src/features/tracking/native/tracking-bridge.ts`, `src/lib/native/tracking-plugin.ts`: `setDeviceToken` replaces `setAccessToken`.
- `src/features/tracking/components/device-token-on-launch.tsx` (new), `src/components/layout/app-shell.tsx`: the launch rule.
- `src/features/tracking/components/duty-screen.tsx`: the token after going on duty.
- `src/lib/auth/session-store.ts`: the hand-off removed.
- `src/mocks/handlers/visits.ts`: `POST /tracking/device-token`.
- `mobile/android/…/tracking/`:
  - `DeviceTokenStore.kt` and `core/DeviceToken.kt` are new;
  - `UploadRunner.kt`, `TrackingPlugin.kt`, `OkHttpTransport.kt` and `core/Uploader.kt` are changed;
  - `AccessTokenHolder.kt` is removed.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: TRK-009.
- Records: `AGENTS.md` §6, `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/handoff-mobile-app.md`, `mobile/README.md` and `docs/Backend-Tasks.md`.

## Tests

- **`device-token.test.tsx` (new):**
  - callers that arrive together share one call;
  - a later call goes under a new key;
  - the expiry goes over in milliseconds and UTC;
  - an answer with no token hands nothing over;
  - a dealer is refused;
  - on launch, the token is asked for only in the app and only on duty.
- **`duty.test.tsx`:**
  - going on duty runs duty start, tracker start, the token, then the hand-over;
  - a token failure leaves the duty on.
- **`session-store.test.ts`:** signing in and out inside the app hands the tracker nothing.
- **Kotlin, `DeviceTokenTest` and `UploaderTest`:**
  - the expiry margin, and a blank token is never sent;
  - a `403` keeps the points and the key;
  - after a `401` the same body goes again under the same key with the new token.
  - The Kotlin core was compiled and its 18 JVM tests run here. The Android build and lint run in CI.
