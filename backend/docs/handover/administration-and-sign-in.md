# Administration and sign-in: what the frontend builds next

> For the frontend track. Everything here is live on the `backend-foundation` branch of the shared repository. The contract is the generated API documentation under `backend/docs/api/`: `users.md`, `org-units.md`, `territories.md`, `partners.md`, `lookups.md`, `auth.md`. This note is the context those files do not carry: what the screens are, in what order to build them, the states to render, and the handful of rules the server enforces that the UI should reflect before the user hits them.

The two contracts before this one, `12-Auth-API-Contract.md` and `13-Leads-API-Contract.md`, still hold. Nothing in them changed shape. One field was added to one response, described at the end.

---

## 1. The one-minute summary

- **Administration is complete on the API:** people (staff and partner users), offices, territories, partners, and the roles lookup. Twenty-five endpoints, all under `/api/v1`, all in the generated docs.
- **A new person gets a temporary password.** Their first sign-in is forced to change it: every endpoint answers `403 password_change_required` until they do, except `GET /auth/me` and `POST /auth/password`. The app needs one screen for that.
- **Dealers and farmers get their sign-in code on WhatsApp.** The request endpoint is unchanged; its 202 now says `"channel": "whatsapp"`. Two sentences of wording on the sign-in screens are the whole frontend change.
- **The conventions from the earlier contracts apply everywhere:** `{data}` on success, `{error: {code, message, fields?}}` on failure including 422, `Idempotency-Key` on every POST and PATCH except the `/auth` mutations, keyset paging with `meta.next_cursor`, an empty list means "nothing in your scope" and a 403 means "not permitted", which the UI treats differently.

---

## 2. Build order

1. **Change password** (one screen). It is on the critical path: the first staff account created through the API cannot use the app until this exists.
2. **People list and person detail**, with create. This is what an administrator opens first.
3. **Offices and territories.** Trees; read-mostly.
4. **Partners.** A list for staff; a subtree for a signed-in dealer.
5. **Handover.** A small dialog from the person screen.
6. **Sign-in wording** for the OTP door (two sentences).

---

## 3. Screens

| Screen | Shows | Actions | Notes |
|---|---|---|---|
| People list | name, type, role, office or partner, active, last sign-in, open leads (staff only) | new person, filter, search | administrators and the Board (read-only); everyone else gets 403 on the module, never an empty list |
| Person | identity, role, anchor (office or partner), territories, created by; for administrators also lockout and live sessions | edit, set password, sign out everywhere, unlock, deactivate or reactivate, hand over, delete | the caller's own row hides role, office, territories and active edits (the server answers 422 otherwise). Delete is disabled while `open_leads > 0`, with hand-over beside it. Unlock and set-password are hidden for partner users |
| New person | staff or partner-user form; role picker from `GET /lookups/roles` filtered on `is_portal`; office tree; territory multi-pick; partner picker | create | the temporary password is shown once; the administrator passes it on out of band |
| Handover | the leaver, a person picker (`GET /leads/assignees`), the count of open leads, a deactivate checkbox | confirm | one request per batch of 500; repeat while `remaining > 0`; show `leads_moved` |
| Change password | current and new | change | shown when `/auth/me` says `must_change_password: true`; every other screen is refused by the server meanwhile; after success the app signs in again |
| Offices | the tree with active user counts | add, rename, move, change territory, close, reopen | close is disabled while users are active, and refused by the server if tried |
| Territories | state, district, taluka, village | add, rename, set code | a state without a code cannot number leads; a code with leads under it is read-only |
| Partners | list scoped to the caller; a dealer sees its subtree | add (a dealer: one type down, under itself), edit, close, reopen | a dealer's edit form shows contact fields only; no move; GSTIN format checked; credit limit stored, not enforced |
| Sign-in, mobile step | "We will send a 6-digit code to this number on WhatsApp" | request the code | this sentence is the WhatsApp opt-in; keep it on the screen where the number is typed |
| Sign-in, code step | "Check WhatsApp for your code", the number, a resend affordance after `resend_after` | enter the code; resend | a resend replaces the earlier code: say so. The WhatsApp message has a copy-code button, so paste works |

---

## 4. People: the rules the UI should reflect

**Shapes.** Every key is always present in a row; `null` means "not set", never "hidden". `open_leads` is filled for staff and `null` for partner users. `locked_until` and `active_sessions` are filled only when the caller holds `users.edit`; render them as absent otherwise.

**Create** (`POST /users`, `UserCreate`):

- `user_type` is `staff` or `partner_user`. Consumers are not created here.
- Staff: `email` (unique among live people, lower-cased by the server), `role` (a code from `GET /lookups/roles` whose `is_portal` is false; the server refuses a portal role on staff), `org_unit_id` (an open office), `territory_ids` (a role that reads any module at territory scope needs at least one, or the person sees nothing there; the server answers 422 on `territory_ids` when the role needs one and none is given), `password` (a temporary password, at least 12 characters, shown once).
- Partner users: `mobile` (any Indian form; stored as `91XXXXXXXXXX`; unique among live people), `partner_id` (an active partner). No role: it follows the partner's type.
- A partner user signs in by OTP and has no password; unlock and set-password do not apply.

**Correct** (`PATCH /users/{id}`, `UserPatch`): send only what changes. A person cannot change their own role, office, partner, territories or active flag: the server answers 422 with a field message, so hide those controls on the caller's own row. Changing a role to one that reads at territory scope, on a person with no territories, is refused with `fields.territory_ids`; the form should ask for territories in the same step.

**Deactivate** (`is_active: false`): every session of the person is signed out first. Reactivation needs an open office or an active partner.

**The last administrator.** The server refuses any change that would leave no active user whose role holds `users.edit`: a 422 with `fields.id` naming the last administrator. Show it as a plain message; there is no way around it by design.

**Set password** (`POST /users/{id}/password`): a new temporary password; every session of the person is signed out; they must change it at the next sign-in. **Sign out everywhere** (`POST /users/{id}/sessions/revoke`) returns how many sessions were live. **Unlock** (`POST /users/{id}/unlock`) clears a sign-in lockout (five failed passwords in fifteen minutes); `was_locked` says whether one was in force.

**Handover** (`POST /users/{id}/handover`, `HandoverRequest`): `to_user_id` from `GET /leads/assignees`, `deactivate` optional. Moves at most 500 open leads per call; `remaining` says how many are left; repeat with a new `Idempotency-Key` until it is 0. With `deactivate: true` the leaver is deactivated once nothing remains; it is refused while `remaining` is above zero, and never on the caller's own row.

**Delete** (`DELETE /users/{id}`): soft delete, refused while the person owns open leads (hand over first). Deleted people are returned only to `users.delete` holders and never in the list.

**Search** (`GET /users?q=`): matches name and email as substrings; matches mobiles only when `q` is a number.

---

## 5. The forced password change

After an administrator creates a staff account, or resets a password, the person signs in with the temporary password and gets a normal token bundle. From then until they change it:

- `GET /auth/me` returns `must_change_password: true`.
- Every other endpoint answers `403` with `code: "password_change_required"`.
- `POST /auth/password` (`current_password`, `new_password`, at least 12 characters, `Idempotency-Key` required) accepts the change and signs out every session, this one included. The app then signs in again with the new password.
- `409 password_changed_meanwhile` means an administrator reset the password while the person was changing it: sign in with the password the administrator gave.

Build the change-password screen so that a `403 password_change_required` from anywhere routes to it, rather than only checking the flag at sign-in.

---

## 6. Offices, territories, partners

**Offices** (`/org-units`): create, rename, move (the server rebuilds the tree; a cycle is 422), change the covering territory, close (refused with a message while active users are anchored on it), reopen. The list carries the active user count per office for the tree screen.

**Territories** (`/territories`): four levels, state, district, taluka, village, each under the level above. Names are unique under a parent; codes per level. A state's code is what numbers leads (`POL/GJ/…`), so a state without a code cannot take leads, and a code that already numbered leads is read-only (`code_locked` in the row). The lead form's picker, `GET /lookups/territories`, is unchanged.

**Partners** (`/partners`): a typed tree, distributor over dealer over sub-dealer, one level per edge, never under a closed parent. Staff see what their scope allows; a signed-in dealer sees its own subtree and may create the next type down under itself. A dealer's own edit is limited to contact fields; the pricing fields (`credit_limit`, `payment_terms_days`, `price_tier`, the type, the territory) are staff-only and come back as `null` to a partner caller, never absent. Close signs the partner's users out (`users_inactive` says how many); reopen restores the row only.

**Roles** (`GET /lookups/roles`): sixteen, never `system`. `code` is what `POST /users` takes as `role`; `is_portal` marks a partner user's role (filter those out of the staff form); `level` runs from 1 (field officer) to 5 (head office).

---

## 7. Sign-in by code: the change

`POST /auth/otp/request` and `POST /auth/otp/verify` keep their shapes and their rules: always 202 on request, with the same body whatever the number; six digits; five minutes; five attempts; the resend cooldown of five minutes that the earlier contract explains.

The 202 gains one field:

```jsonc
{ "data": { "sent": true, "channel": "whatsapp", "expires_in": 300, "resend_after": 300 } }
```

`channel` is a deployment-wide constant. Render it in the wording; do not branch on it. The code arrives as a WhatsApp message with a copy-code button. A resend replaces the earlier code, so the earlier one stops working the moment the new one is issued: the code screen should say "we sent a new code; the earlier one no longer works" after a resend.

Two sentences to add: on the mobile step, "We will send a 6-digit code to this number on WhatsApp"; on the code step, "Check WhatsApp for your code".

---

## 8. Error codes to handle

| Code | Status | When |
|---|---|---|
| `validation_error` | 422 | a field failed; `fields` maps field path to reason. Render beside the field |
| `password_change_required` | 403 | a temporary password is in force; route to the change-password screen |
| `insufficient_permission` | 403 | the action is not in the caller's permissions; hide the control next time |
| `not_found` | 404 | no such row in the caller's scope (also how a hidden row answers) |
| `idempotency_key_reused` | 409 | the key was used for a different body; generate a new key per user action |
| `password_changed_meanwhile` | 409 | on `POST /auth/password`; sign in with the administrator's password |
| `unauthenticated` | 401 | refresh or sign in again |

---

## 9. Where to look

- `backend/docs/api/users.md`, `org-units.md`, `territories.md`, `partners.md`, `lookups.md`, `auth.md`: the field-by-field contract, regenerated from the live OpenAPI after every change.
- `/openapi.json` on the development server for a client generator; `/docs` for the interactive view.
- Anything that looks like a breaking change to an existing shape is a conversation first: the earlier contracts stay as they are.
