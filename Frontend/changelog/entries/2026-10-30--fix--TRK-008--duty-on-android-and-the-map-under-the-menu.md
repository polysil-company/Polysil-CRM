---
date: 2026-10-30
type: fix
title: Duty on Android, and the map under the menu
dataIds:
  - TRK-008
  - TRK-001
author: Nakul Srivastava
breaking: false
---

## Before

The first trial on a phone (APK 0.1.1, 30 Oct) found two bugs:

- **Duty showed "Something went wrong"** whenever the person was off duty.
  - The tracker reports its status with the duty, start time, last upload and error left empty. Android's JSON (`org.json`) drops a key whose value is null instead of sending `null`.
  - The status schema required each key, so the whole answer was refused.
  - The same refusal also stopped the device token's renewal on launch (TRK-009), since that reads the same status.
  - Tests never caught it, because they replace the tracker with a stand-in that sends every key.
- **The Team map covered the phone menu.** Leaflet stacks its panes and controls at z-index 400 to 1000, above the app's menu sheet (layer 40 to 80).

## Now

- **The status schema reads a missing field as empty (`null`).** Off duty, Duty shows the toggle and the setup cards. This is a web fix, so it reaches phones without a new APK.
- **The map keeps its layers inside its own box** (`isolate` on `MapView`). The menu, dialogs, popovers and toasts draw over it everywhere it's used: Team map, a person's route, and visit check-in.

## Discussion

- **Why a web fix rather than an Android one:** the Kotlin side could send `JSONObject.NULL` instead, but that needs a new APK on every phone. Reading a missing key as null fixes the phones already installed, and stays right if the Kotlin side changes.
- **Not changed:** the other tracker answers (permissions, device, flush) never carry an empty field.

## Files changed

- `src/features/tracking/native/tracking-bridge.ts`: `emptyAsNull` for `dutyId`, `since`, `lastUploadAt` and `lastError`.
- `src/components/patterns/map-view.tsx`: `isolate` on the map's frame.
- `src/features/tracking/native/tracking-bridge.test.ts`: the status as Android sends it.
- `Docs/screenshots/tracking/team-map-menu-open-phone-light.jpg`.

## Tests

- `tracking-bridge.test.ts`:
  - the off-duty answer `{ onDuty: false, pendingPoints: 0 }` reads with every empty field as `null`;
  - an on-duty answer keeps what it sends.
- **Map:** at 360 px in the mock, with the menu open over Team map, the point under the menu belongs to the menu, not the map (checked with Playwright; screenshot linked above).
