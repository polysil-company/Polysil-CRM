# Polysil for Android (TRK-008)

The Polysil app for field staff. It opens the same Polysil you use in a browser, and adds one thing a browser can't do: **while you're on duty, it records your route**, so the day's kilometres and your visits show on the route page.

## Install it (for staff)

Your administrator sends you a file named `polysil-tracking-<version>.apk`.

1. **Open the file on your phone.** If Android says it can't install apps from this source, tap **Settings** and turn on **Allow from this source** for the app you opened it with (Files, Chrome or WhatsApp). Go back and tap **Install**.
2. **"Unverified developer".** From 2027 in India, Google asks once before installing an app from a developer it hasn't verified. If you see this, follow the steps on screen: Android may ask you to restart the phone and wait 24 hours before the install goes through. This goes away once the company registers as a developer with Google.
3. **Sign in** with your work email and password, as on the web.

## Before your first duty

Open **Duty** from the menu. Each card that shows is one thing to do; **Go on duty** turns on once they're all done.

- **Location: "Allow all the time".** Needed so your route keeps recording with the screen off. Only while you're on duty.
- **Battery optimisation: off for Polysil.** Otherwise the phone stops the app to save battery and your route has gaps.
- **Notifications: allowed** (Android 13 and up). Android shows "Tracking on duty" while your route is recorded.
- **Location (GPS): on.**
- **Autostart** (Xiaomi, Redmi, POCO, Oppo, Realme, Vivo, OnePlus, Samsung). These phones can stop apps in the background. Duty links to your phone's page on dontkillmyapp.com; follow it once. The app can't check this setting, so it's advice, not a blocker.

## Every day

- **Go on duty** when you start work, and **Go off duty** when you finish. Your location is recorded only in between.
- No signal? Keep working. Points wait on the phone and go up when the connection is back.
- The server ends a duty left on after working hours.

## For developers

- **What it is:** a Capacitor shell that loads the live web app (`capacitor.config.ts`, `server.url`), plus our own Kotlin plugin under `android/app/src/main/java/com/polysil/crm/tracking/`:
  - Play Services' Fused location;
  - a foreground service of type `location`;
  - Room, which keeps every point until the server counts it;
  - OkHttp for the uploads, never the WebView;
  - WorkManager as the backup when the network comes back.

  The upload rules live in plain Kotlin (`tracking/core/`) with JVM unit tests. The web side is `Frontend/src/features/tracking/native/` and the Duty screen.
- **Which site it opens:** `CAP_SERVER_URL` when you run `npx cap sync android`; the staging web app without it. A production APK must set it. Only https, no cleartext, and navigation stays on that host. Capacitor documents `server.url` as meant for live reload; we use it on purpose so screen changes need no new APK.
- **Build locally:** Node 24, JDK 21, the Android SDK (platform 36).
  ```bash
  npm ci
  npx cap sync android
  cd android && ./gradlew lint test assembleDebug
  ```
- **Release:** run **Actions → Android APK → Run workflow**. It builds `polysil-tracking-<version>.apk`, signed with the keystore from the repository secrets (`POLYSIL_KEYSTORE_BASE64`, `POLYSIL_KEYSTORE_PASSWORD`, `POLYSIL_KEY_ALIAS`, `POLYSIL_KEY_PASSWORD`).
  - The keystore never goes in the repository: `*.jks` and `*.keystore` are ignored.
  - Bump `versionCode` and `versionName` in `android/app/build.gradle` on every release.
  - A change to the web app alone needs no new APK.
- **Versions:**
  - Capacitor 8.5.3 and its template's Android Gradle Plugin 8.13.0, Gradle 8.14.3, SDK 36, minimum Android 7 (API 24).
  - Kotlin 2.4.21, KSP 2.3.12.
  - Play Services Location 21.4.0, Room 2.8.4, WorkManager 2.11.2, OkHttp 5.5.1, kotlinx-serialization-json 1.12.0.
- **Waiting on BE-032 (a device token):** the native side uploads with the web session's access token, handed over by `Frontend/src/lib/auth/session-store.ts`, until that token expires.
  - Points then wait on the phone, nothing is lost, and they go up when the app is next opened.
  - Until BE-032 lands, the team map shows staff as stale while the app is closed.
  - Once it lands, Duty requests the device token at start and keeps it in encrypted storage.
