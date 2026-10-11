---
date: 2026-10-10
type: feature
title: "Users and roles: people, accounts and leavers"
dataIds:
  - ADMN-001
  - ADMN-002
  - ADMN-003
  - ADMN-004
  - ADMN-005
  - ADMN-006
author: Nakul Srivastava
breaking: false
---

## Before

The backend has served people administration for a while (`backend/docs/api/users.md`, handover `administration-and-sign-in.md`, twenty-five admin endpoints). On screen, **Admin → Users & roles** was a "Soon" placeholder. Nobody could add a staff member or a dealer's user, reset a password, unlock an account or hand a leaver's leads over without going to the backend.

## Now

- **Admin → Users & roles** (`/users`, staff with `users`):
  - every staff member and partner user in scope, newest first;
  - each row shows how they sign in, their role, their office or partner, the last sign-in, open leads, and "Deactivated" or "Temporary password";
  - search by name, email or mobile; filter by type, role and status, all in the URL;
  - **Download Excel**, and **New person** for whoever may add people.
- **A person** (`/users/{id}`):
  - **Sign-in:** email or mobile, last sign-in, the password's state, a live lockout with its end, live sessions.
  - **Role and place:** role, office or partner, territories, open leads, and who added them when.
  - **Edit**, and under **More**: set a temporary password, unlock sign-in (while locked out), sign out everywhere, hand over leads and tasks, deactivate or reactivate, delete.
  - **Delete** is disabled while they own open leads, saying to hand over first.
  - **Your own row** is marked "You". It offers no deactivate or delete, and the edit form keeps your role, office and territories read-only, as the backend refuses them.
- **New person** (`/users/new`):
  - **Polysil staff:** name, work email, optional mobile, a staff role (portal roles left out), an open office (searched), territories (added one at a time, removable), and a suggested temporary password that can be regenerated.
  - **Partner user:** name, mobile, partner; their role follows the partner's type.
  - **Once added**, a staff member's temporary password is shown once, with Copy and a reminder to pass it on in person or by phone. Then their page, or another person.
- **Edit** (`/users/{id}/edit`): the same form. Only what changed is sent, and Save stays off until something has.
- **Set a temporary password:** a suggestion or your own (12+ characters). It says how many sessions were signed out, and shows the password once. The person then meets #89's forced change.
- **Hand over:**
  - choose who takes the work over, from those who can work leads;
  - optionally deactivate the leaver once nothing remains;
  - the dialog repeats in batches of 500, each with a new key, while the backend says some remain, then says how many leads and tasks moved.
- **Refusals land where they belong.** A taken email, a short password or a territory role without territories go on their field. The last administrator, or anything else, shows above the buttons.

## Discussion

**Decisions:**

- **Pages for the form, dialogs for the actions.** Adding or correcting a person is a long form with pickers, so it gets a page. Every account action is a single confirmation, so it gets a dialog that says what happens before it does.
- **A suggested temporary password.** Four groups of four characters with no look-alikes (`Kp7m-Rq4x-Tz9w-Hb3n`), from `crypto.getRandomValues`: over the minimum of 12, and easy to read out by phone. It is shown after saving and never again; the API never returns it.
- **The client's own role and territory rules aren't guessed.** Whether a role needs territories is the backend's answer (`fields.territory_ids`). The form says what territories are for and puts the refusal on the field.
- **The partner picker is the complaints' `DealerPicker`** (any partner type, by name, code or contact person), reused rather than copied.
- **The faded avatar for a deactivated person was dropped.** axe flagged its contrast, and the "Deactivated" badge already says it.

**The mock:**

- People (`mockDb.users`): the signed-in admin (usr-001), the staff who own the mock's leads and tasks, three head-office desks, a deactivated officer, a new joiner with a temporary password, and one user per channel partner.
- Ravi Joshi is locked out for the next few minutes, to show unlock.
- `GET /org-units` (with a closed office) and the sixteen roles of `identity.ASSIGNABLE_ROLES`. The role names and levels are the mock's own.
- The backend's rules:
  - email and mobile unique among live people;
  - a staff role and an open office;
  - territories for the territory roles;
  - nothing changed on your own row;
  - the last administrator kept;
  - delete refused while open leads remain;
  - handover in batches of 500, moving open tasks too;
  - idempotent replays of `POST /users`.

## Files changed

- `src/features/users/`: new.
  - `api/users.{schemas,api,queries,mutations}.ts`, with `users.test.ts`;
  - `components/users-list.tsx`, `person-detail.tsx`, `person-dialogs.tsx`, `person-form.tsx`, `person-pages.tsx`, `office-picker.tsx`, with `users-ui.test.tsx`;
  - `hooks/use-user-list-params.ts`, `lib/user-labels.ts`, `lib/temporary-password.ts`.
- `src/app/(app)/users/`: the list, `new`, `[userId]` and `[userId]/edit` routes.
- `src/components/layout/navigation.ts`: Users & roles is a link now, with its description.
- `src/mocks/data/users.ts`, `src/mocks/handlers/users.ts`: new. `src/mocks/db.ts`, `handlers/index.ts`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: ADMN-001 retitled, ADMN-002…006 new.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/users/`: the records.

## Tests

**`src/features/users/api/users.test.ts`:**

- `[ADMN-001]`: the list with a total and open leads for staff only; role, status and mobile filters; the export; the sixteen roles, three of them portal.
- `[ADMN-003]`:
  - a staff member with a temporary password, then a replay of the same key, and a 409 for a different body;
  - a short password, a taken email and a territory role without territories, all refused on their fields;
  - a partner user, mobile normalised, role from the partner.
- `[ADMN-004]`: your own role refused but your name changed; deactivate and reactivate.
- `[ADMN-005]`: unlock, a temporary password signing a session out, sign out everywhere; no password for a partner user.
- `[ADMN-006]`: delete refused with open leads, then handover with deactivate, then delete; never your own row.

**`src/features/users/components/users-ui.test.tsx`:**

- the list's rows and badges;
- partner users from the URL;
- no New person for whoever may only look;
- the person page with every action, Delete disabled while leads remain;
- your own row;
- a temporary password set and shown once;
- a handover with deactivate;
- New person: missing fields, then added with its password shown;
- a taken email on its field;
- Edit sending only the name.

**By hand, in Chromium on the mock backend, as an Admin:**

1. The list on a desktop.
2. Ravi Joshi's page and its actions: a temporary password set and shown, then a handover to Nirav Shah with deactivate.
3. New person: with every field empty, then a field officer for Rajkot District with a territory.
4. On a 360 px phone in dark mode: the list, your own page, and the partner-user form.

axe found nothing (after dropping the faded avatar); no sideways scroll on the phone.
