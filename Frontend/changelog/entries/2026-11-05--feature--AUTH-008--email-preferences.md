---
date: 2026-11-05
type: feature
title: Email preferences
dataIds:
  - AUTH-008
author: Claude
breaking: false
---

## Before

- The backend's FS-078 (migration 082) can email two things:
  - notifications still unread 10 minutes after they arrive, several in one email;
  - a morning summary at 08:00 IST, Monday to Saturday, of the day's due and overdue tasks.
- **The switches:** each person turns them on or off with `PUT /me/email-preferences`. `GET /auth/me` says where they stand (`email_preferences`) and whether email can reach the person at all (`email_available`).
- The frontend had no way to set them.

## Now

- **An Email item in the account menu**, only while `email_available` is true. That is false until the CRM has a mail account, and for anyone without a usable address, so today it stays hidden.
- **It opens two switches,** as they stand: **Updates I haven't seen** and **Morning summary**, each saying what it sends and when.
- **Save** is off until something changes, and sends both, as the backend requires. "Email preferences saved", then the session reads them again.
- **A backend before 082** sends neither field: email reads as unavailable, with both switches on (the backend's defaults).

## Discussion

- **Hidden rather than greyed out.** The backend says to hide the switches while email is unavailable. A greyed-out item would promise a feature that can't work yet.
- **Checkboxes, not toggles.** The design system has no switch component, and a checkbox with its line of explanation reads the same. A switch can replace them if one is added to the design system later.
- **The mock** says email is available, so the switches can be tried. It keeps them per session, both on to start, as the backend seeds, and refuses a farmer's portal account.

## Files changed

- `src/features/session/api/session.schemas.ts`: `email` on the session (available, notices, morning summary).
- `src/features/auth/api/auth.schemas.ts`, `auth.api.ts`, `auth.mutations.ts` (new): the call and its mutation.
- `src/features/auth/components/email-preferences-dialog.tsx` (new): the switches.
- `src/components/layout/user-menu.tsx`: the Email item.
- `src/mocks/handlers/auth.ts`, `src/mocks/db.ts`: the fields on `/auth/me`, and the PUT.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: AUTH-008.
- `Docs/Plan.md` §9.1, `Docs/plan-13oct-2026.md`, `Docs/Tested-Features.md`: records.

## Tests

- **`[AUTH-008] Email preferences in the account menu`:** no item while email is unavailable; the switches open as they are, with Save off.
- **`[AUTH-008] EmailPreferencesDialogContent`:** turning the morning summary off saves both switches.
- **`[AUTH-002]`:** the session contract test now expects the email defaults from a backend before 082.
