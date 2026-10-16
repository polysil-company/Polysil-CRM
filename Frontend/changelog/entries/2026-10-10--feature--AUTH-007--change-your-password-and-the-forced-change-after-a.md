---
date: 2026-10-10
type: feature
title: Change your password, and the forced change after a temporary one
dataIds:
  - AUTH-007
author: Nakul Srivastava
breaking: false
---

## Before

An administrator creates a staff member with a temporary password, or resets one (`POST /users`, `POST /users/{id}/password`). Until that person changes it, the backend refuses every call but `GET /auth/me` and `POST /auth/password` with `403 password_change_required` (handover `administration-and-sign-in.md`, step 1 of its build order).

The app had no change-password screen, didn't read `must_change_password`, and treated those 403s like any other refusal. So a newly created staff account could sign in and then do nothing. Nobody could change their own password either.

## Now

- **The forced change.**
  - While `/auth/me` says `must_change_password`, the app shows only **Choose your own password**, in the sign-in frame: the temporary password, then the new one twice.
  - **Not you? Sign out** is below it.
  - The app waits for `/auth/me` before rendering anything, so a first load never fires a burst of refused calls.
  - A `403 password_change_required` from any query or mutation (an administrator reset the password mid-visit) switches to the screen at once.
- **The voluntary change.** Staff get **Change password** in the account menu, which opens the same form in a dialog. Partners sign in by code and don't see it.
- **After the change**, the backend signs out every session. The app ends the session and opens sign-in on the email form, saying "Password changed. Sign in with your new password."
- **409 `password_changed_meanwhile`** (an administrator reset it in between) also ends the session. Sign-in then says to use the password the administrator gave.
- **Field errors.**
  - A wrong current password reads "That isn't your current password." The field is cleared and focused, and the new password is kept.
  - The new password's length (12 to 128, the backend's only rule) and a mismatched repeat are checked before sending.
- **The API client now sends an Idempotency-Key on `POST /auth/password`**, which requires one. Only login, OTP, refresh and logout go without.

## Discussion

**Decisions:**

- **A gate, not a route.** The forced change replaces the app inside the session gate, rather than living at `/change-password`. Every other page would only show refusals, and no link or back button can get round it.
- **Sign in again, rather than signing in automatically.** The backend ends every session, this one included, and `/auth/me` carries no email to sign in with. The sign-in page opens on the email form with the reason, so it is one step.
- **No password rules of our own.** The form checks the length the backend enforces and that the repeat matches, nothing more (rule 10).
- **`BrandMark` moves to `components/patterns`.** The forced screen reuses the sign-in frame (`AuthFrame`, now shared with the `(auth)` layout), and features may not import the layout.

**The mock:**

- The account menu's mock section gets a **Temporary password** switch. While it is on, `/auth/me` says so and every other call answers 403 `password_change_required`, as the backend does.
- `POST /auth/password` checks the current password, the length and the Idempotency-Key, then signs every session out.
- Sign-in then accepts the new password as well as the demo one, so a demo can't lock itself out.

## Files changed

- `src/features/auth/`:
  - `components/change-password-form.tsx`, `forced-password-change.tsx`, `change-password-dialog.tsx`, `auth-frame.tsx`: new;
  - `components/auth-gate.tsx`: the password-change gate;
  - `components/sign-in-screen.tsx`: the two new notices, the email form first;
  - `api/auth.api.ts`, `api/auth.schemas.ts`: `changeOwnPassword` and the form schema;
  - tests: `change-password.test.tsx` (new), `auth-gate.test.tsx`.
- `src/features/session/api/session.schemas.ts`: `mustChangePassword`, with its test.
- `src/lib/auth/redirects.ts`: the `password-changed` and `password-reset` end reasons.
- `src/lib/api/client.ts`: the keyless `/auth` paths named, with its test.
- `src/components/layout/user-menu.tsx`: Change password and the mock switch, with its test. `components/patterns/brand-mark.tsx`: moved from `layout/`.
- `src/app/(auth)/layout.tsx`: uses `AuthFrame`.
- `src/lib/dev/mock-settings.ts`, `src/mocks/handlers/auth.ts`: the mock.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: AUTH-007.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/auth/`: the records.

## Tests

**`src/features/auth/components/change-password.test.tsx`:**

- the three fields checked before anything is sent: empty, too short, not matching;
- a wrong current password named on its field, cleared, with the new one kept;
- both passwords sent with an Idempotency-Key, then the session ends with `password-changed`;
- a reset meanwhile ends it with `password-reset`;
- the sign-in notices for both, on the email form.

**`auth-gate.test.tsx`:**

- the app waits for `/auth/me`;
- only the password change shows while a temporary password is in force;
- a refused query switches to it.

**`user-menu.test.tsx`:** staff get Change password in a dialog; a dealer doesn't.

**`session.schemas.test.ts`:** `must_change_password` read, false when missing.

**`client.test.ts`:** the key on `/auth/password`, none on `/auth/login`.

**By hand, in Chromium on the mock backend, as an Admin:**

1. The account menu's dialog.
2. The Temporary password switch, then the forced screen.
3. A wrong temporary password, then the right one.
4. Signed out to "Password changed", then signed in with the new password.
5. The forced screen on a 360 px phone in dark mode.

axe found nothing; no sideways scroll on the phone.
