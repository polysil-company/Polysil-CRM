---
date: 2026-10-02
type: api-integration
title: "Notifications and messages on the backend"
dataIds:
  - NOTIF-001
  - NOTIF-002
  - MSG-001
  - MSG-002
  - MSG-003
  - MSG-004
  - MSG-005
  - APP-004
author: Nakul Srivastava
breaking: false
---

## Before

The bell and staff messages were built on a contract the frontend proposed (15 September), and ran on the mock backend even against a real API: `partial` mocking kept them in `unbuiltHandlers`. The backend has served both since #31 (BE-009, BE-010), close to that proposal but with differences the screens did not handle yet.

- **The bell polled the whole list.** It fetched 20 notifications every 30 seconds. The backend asks the bell to poll `?limit=1` for the count; there is no push.
- **Only three notification kinds had an icon.** The backend sends fourteen.
- **Quotation and sales order notifications opened nothing.** Both screens exist now.
- **Marking a conversation read sent no `up_to`.** A message that arrived while the call ran was marked read unseen.
- **Colleagues who left weren't handled.** The backend marks them `is_active: false` and refuses a message with `422 participant_inactive`; the composer said only "Couldn't send".
- **Unshareable leads weren't explained.** A lead the sender can't see is refused with `422` on `resource`.
- **A new conversation lost its name.** The backend lists a conversation only once someone writes in it, so a conversation just opened from the directory had no name in its header.

## Now

- **Bell (NOTIF-001, NOTIF-002)**
  - **Polling.** The badge polls `GET /notifications?limit=1` every 30 seconds. The list of 20 is read when the bell opens, and polled only while it stays open.
  - **Icons and links.** Each of the backend's 14 kinds has its own icon; an unknown kind gets the plain bell. A notification about a lead, quotation or sales order opens it; tasks and complaints have no screen yet.
  - **Marking read.** Marking one or all read updates the list and the badge at once, restores both if the call fails, then takes the backend's new count.
  - **Unknown names.** An actor whose name the backend leaves blank names nobody, instead of failing the contract.
  - **Contrast fix.** The bell's time and record line uses `muted-foreground`. The subtle shade measured 4.27:1 against the dark popover, below the 4.5:1 minimum.
- **Messages (MSG-001…005)**
  - **`up_to`.** Opening a conversation marks it read up to the newest message on screen (`up_to`).
  - **A colleague who has left** is shown as such. The conversation stays readable, with a notice in place of the message box. If the backend refuses a send because they have left, the notice appears and the draft stays, read-only, to copy.
  - **Refusals.** A lead the sender can't see is refused with a reason: "This lead can't be shared…".
  - **A new conversation** keeps its colleague's name and the "Say hello to …" prompt from the `POST /conversations` answer. Its first message then lists it.
- **`partial` mocking now mocks nothing (APP-004).** `unbuiltHandlers` is empty, so every request goes to the real API, and no screen is mocked against a live backend.
- **Mock backend** now behaves like the real one:
  - error codes: `validation_error` with fields, `insufficient_permission`, `not_found`, `participant_inactive`;
  - only written-in conversations are listed;
  - the directory offers active staff only;
  - `up_to` marks read only so far and refuses a message from another conversation;
  - leads are labelled with their inquiry number;
  - a colleague who has left (Meera Iyer) is seeded with an old conversation;
  - the seeded notifications point at a real mock quotation and order.

## Discussion

- **Count and list are two queries, as the backend suggests.** The count query is tiny and always on. The list query runs only while someone looks. The badge shows whichever answered last, so opening the bell never shows two different counts.
- **A colleague who has left: notice instead of box.** An empty box that can't send invites typing that goes nowhere. The box comes back read-only only when it already holds a draft, so nothing written is lost.
- **Older messages are not paged yet.** The thread shows the latest 50 (`TODO(MSG-002)`, `meta.next_cursor` is there). Enough for every conversation so far.
- **Asked of the backend: BE-021.** `GET /conversations/{id}` (or listing a conversation once opened), so an empty conversation still has a name after a reload.
- **Contrast is fixed locally, not in the token.** `subtle-foreground` is 4.27:1 on the dark popover; changing the token would move every screen. Worth a look in the design tokens.
- **Partial mode's lead seam is gone.** The mock used to trust real lead ids in partial mode; it no longer needs to, since partial mode no longer mocks messages.

## Files changed

- **Notifications**
  - `src/features/notifications/api/notifications.schemas.ts`: the 14 kinds; blank actor names.
  - `notifications.api.ts`: `countUnreadNotifications`.
  - `notifications.queries.ts`: count and list queries.
  - `notifications.mutations.ts`: optimistic list and badge.
  - `lib/mark-read.ts`: `unreadAfterMarking`.
  - `components/notification-bell.tsx`: count polling, list on open, icons, contrast.
  - `src/lib/navigation/resource-href.ts`: quotation and sales order links.
- **Messages**
  - `src/features/messages/api/messages.schemas.ts`: `is_active`; the mark-read body.
  - `messages.api.ts`: `up_to`.
  - `messages.queries.ts`: the started conversation.
  - `messages.mutations.ts`: the read variables; the first message lists a conversation.
  - `lib/send-refusal.ts`: new.
  - `components/conversation-thread.tsx`, `message-composer.tsx`: `up_to`, the closed conversation, refusals.
- **Mock backend**
  - `src/mocks/handlers/index.ts`: `unbuiltHandlers` empty.
  - `handlers/notifications.ts`, `handlers/messages.ts`: the backend's rules and codes.
  - `data/notifications.ts`, `data/messages.ts`, `db.ts`: seeds.
- **Records**
  - `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: NOTIF and MSG in progress; LEAD-001's note.
  - `Docs/Plan.md` §9, `Docs/Environments.md`, `Docs/Tested-Features.md`.
  - `../docs/Backend-Tasks.md`: BE-021.
  - `Docs/screenshots/messages-notifications/`.

## Tests

- **`src/features/notifications/api/notifications.api.test.ts`**
  - `[NOTIF-001]` the backend's own page, with a nameless actor.
  - `countUnreadNotifications` sends `limit=1`.
- **`lib/mark-read.test.ts`**: `[NOTIF-002] unreadAfterMarking`.
- **`components/notification-bell.test.tsx`**
  - Only the count is polled until the bell opens. This test fails on the old bell, which fetched 20 at once.
  - Quotation and order links.
- **`src/features/messages/api/messages.api.test.ts`**
  - `[MSG-003]` a lead that can't be shared is refused on `resource`; a colleague who has left gets `participant_inactive`.
  - `[MSG-004]` a conversation is listed after its first message; the directory offers active staff only; a colleague who has left stays readable.
  - `[MSG-005]` `up_to` leaves a later message unread; an `up_to` from another conversation is refused.
- **`components/conversation-thread.test.tsx`** `[MSG-002]`
  - Reads up to the newest message shown.
  - A colleague who has left: notice, no box.
  - A send refused because they left: the notice, and the draft kept read-only.
  - A just-started conversation names its colleague.
- **`lib/send-refusal.test.ts`**: `[MSG-003]` each refusal in words.
- **`src/mocks/handlers/index.test.ts`**: `[APP-004]` nothing is mocked in partial mode.
- **`e2e/smoke.spec.ts`** on desktop and phone, with axe: 6 passed.
  - `[NOTIF-001]` the bell opens a quotation.
  - `[MSG-002]` send a message; a colleague who has left.
- **By hand, with axe:** the bell, a thread and a closed conversation on a desktop (light) and a phone (dark). axe found the bell's contrast issue, fixed here; after the fix, nothing.
