---
date: 2026-10-27
type: feature
title: Polysil's logo everywhere, and phone tests with Maestro
dataIds:
  - APP-010
  - TRK-008
author: Nakul Srivastava
breaking: false
---

## Before

The app used a placeholder: a water droplet on teal. It appeared on sign-in, in the sidebar, the portal, the public pages and the browser tab. The Android app showed Capacitor's default icon and splash. The client asked for the real logo everywhere, and asked how to check the Android app on a phone.

## Now

- **One source for the logo:** the one the backend prints on quotation PDFs, `backend/worker/templates/assets/polysil-logo.png`. `mobile/scripts/make-brand-assets.mjs` cuts the leaf from it and draws every size: the web logo and leaf, the favicon, the Apple icon, the Android launcher icons (legacy, round and adaptive) and the splash screens.
- **Sign-in and the public pages** show the full logo, "POLYSIL · Shaping water". Sign-in keeps "CRM & DMS" beside it.
- **Sidebar, portal and browser tab** show the leaf on a white tile, like the app icon.
- **Android:**
  - the launcher icon is the leaf on white;
  - the splash is the full logo on white;
  - the version is 0.1.1 (code 2), so the new APK installs over 0.1.0.
- **Phone tests:** `mobile/maestro/` holds Maestro flows and a step-by-step guide for a testing agent:
  - smoke tests: launch, sign in, menu pages, sign out;
  - duty tests: setup, on duty, uploads after 10 minutes in the background, off duty;
  - the report format to send back.

## Discussion

- **On white, not see-through.** The logo's white wave line is transparent in the PDF's file, so on a dark screen the page showed through it. Each piece now sits on white, as it does on the PDF. It reads the same in light and dark mode and needs no new colour token.
- **Sharpness.** The logo is only 411 × 101 px. The web shows it near its own size and stays crisp. Android's largest icons enlarge the leaf about 2×, so they're slightly soft. Running the script with a larger logo from the client fixes every size at once.
- **Maestro and the WebView.** On Android WebView 150 and later, Maestro can't find text boxes by name, so the flows tap each field's label, which focuses the box. Duty tests write real duties, so the guide keeps them to a test account or the test site.
- **The mocks' stand-in file link** moves from `/icon.svg` to `/icon.png`, since the tab icon is now a PNG.

## Files changed

- `src/components/patterns/brand-mark.tsx`: `BrandMark` (the leaf tile) and the new `BrandLogo`.
- `src/features/auth/components/auth-frame.tsx`, `src/app/(public)/layout.tsx`: the full logo.
- `src/assets/brand/polysil-logo.png`, `polysil-mark.png`, `src/app/icon.png`, `src/app/apple-icon.png` (new); `src/app/icon.svg` (removed).
- `src/mocks/handlers/*`, `record-documents.test.tsx`: `/icon.png` as the stand-in file link.
- `mobile/scripts/make-brand-assets.mjs` (new); `mobile/android/app/src/main/res/mipmap-*`, `drawable*/splash.png`; `mobile/android/app/build.gradle` (0.1.1).
- `mobile/maestro/` (new): `README.md`, `config.yaml`, `common/`, `flows/`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: APP-010. `Docs/Tested-Features.md`, `mobile/README.md`, `Docs/screenshots/brand/`.

## Tests

- Checked in the mock with Playwright: sign-in at 1440 px light, 1440 px dark and 360 px dark, and the dashboard's sidebar. Screenshots are in `Docs/screenshots/brand/`.
- The Android icons and splash were checked as images; CI builds the APK.
- The Maestro flows parse as YAML. They run on a phone through the guide in `mobile/maestro/README.md`, which can't be done from this sandbox.
