---
date: 2026-11-11
type: fix
title: The phone's back button goes to the previous screen
dataIds:
  - TRK-008
author: Claude
breaking: false
---

## Before

- **The client reported it:** in the Android app, the phone's back button (or the back gesture) closed the app instead of going to the previous screen.
- **Why:** the app is a Capacitor shell around the web app. Capacitor handles back only through its App plugin (`@capacitor/app`), and this app doesn't use it. With nothing handling back, Android closed the app on the first press, whatever screen was open.

## Now

- **Back goes to the previous screen,** like a browser's back:
  - Leads → a lead → back returns to Leads;
  - Tasks → back returns to the screen before it.
- **The app closes only when there is no screen to go back to.** On the first screen, Android does what it does for any app: it leaves the app.
- **APK 0.1.2** (`versionCode` 3) carries the fix. It is a change in the Android shell, so it reaches a phone only when that phone installs the new APK. A web change alone wouldn't need one.

## Discussion

- **How it works:** `MainActivity` adds a callback to Android's back dispatcher. When the web view has history, it goes back in it; when it hasn't, it steps aside and lets Android handle back.
- **Each screen is a history entry** because Next.js pushes each navigation, so going back in the web view returns to the screen before.
- **Why a callback rather than the App plugin:** the plugin would do the same and add a dependency to the APK. The callback is a few lines in the activity the app already has.
- **Why a callback rather than `onBackPressed`:** the APK targets Android 16 (SDK 36). There, the predictive back gesture is on and `onBackPressed` is no longer called; dispatcher callbacks still are.
- **Not changed:** an open dialog or menu still closes with its own close button or a tap outside. Back closes it only where the screen keeps it in the address (a dialog opened with `?…=` in the URL).

## Files changed

- `mobile/android/app/src/main/java/com/polysil/crm/MainActivity.java`: the back callback.
- `mobile/android/app/build.gradle`: `versionCode` 3, `versionName` 0.1.2.
- `mobile/maestro/flows/03b-back-button.yaml`, `mobile/maestro/README.md`: a smoke flow for back.

## Tests

- **CI:** the Android APK workflow compiles and lints the app (`./gradlew lint test assembleDebug`) on this pull request.
- **On a phone:** `03b-back-button` (smoke) opens Leads, then Tasks, then presses back. It checks the app is on Leads, and after a second back that it is still open. Run it with the other smoke flows on APK 0.1.2.
- **Not run here:** there is no Android SDK or phone in this environment, so neither a local build nor the Maestro flow ran before this change went up.
