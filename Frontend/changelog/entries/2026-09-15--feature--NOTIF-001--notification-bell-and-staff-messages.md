---
date: 2026-09-15
type: feature
title: Notification bell in the top bar, and direct messages between staff
dataIds:
  - NOTIF-001
  - NOTIF-002
  - MSG-001
  - MSG-002
  - MSG-003
  - MSG-004
  - MSG-005
  - APP-001
author: Nakul Srivastava
breaking: false
---

## Before

Nothing told a user that work was waiting for them: an approval, a lead or a task assigned to them only showed up if they went looking. Colleagues had no way to talk inside the CRM — conversations about a lead happened on WhatsApp or the phone, away from the record. Neither feature had a backend endpoint or a Data ID.

## Now

**Notifications (NOTIF-001, NOTIF-002)** — a bell in the top bar, on every signed-in page:

- A teal badge shows the unread count (99+ beyond that), and the button's name says it: "Notifications, 3 unread".
- It opens the latest 20: approvals waiting on me, leads and tasks assigned to me — each with an icon, who did it, how long ago and the record it concerns. Unread ones are bold with a dot.
- Clicking one marks it read, and opens its record when that record has a screen (leads today). "Mark all as read" clears everything. Both update the badge at once and roll back if the request fails, with a toast.
- Loading shows skeleton rows; an empty list says "You're all caught up"; a failure shows the error with a reference and a retry. Partner accounts see an empty bell for now.
- New notifications arrive by checking every 30 seconds while the tab is visible, and right away when it comes back.

**Messages (MSG-001 … MSG-005)** — one-to-one conversations between staff, under Messages in the sidebar:

- The sidebar item shows the unread total (a dot in the collapsed rail). Partner users don't see it; opening `/messages` tells them messaging is for staff.
- Desktop and tablet show the conversation list beside the open conversation; phones show one, then the other, with a back button.
- The list shows each colleague, the last message ("You: …" for mine), when, and an unread badge. "New message" searches the staff directory by name, role or office and opens the existing conversation or starts one.
- A conversation groups messages by day and by burst, mine on the right in teal. Opening it marks it read. It keeps the newest message in view.
- The composer: Enter sends and Shift + Enter adds a line on a keyboard; on touch screens Enter adds a line and the button sends. Empty messages can't be sent; over 2,000 characters it says by how much. While sending, the message shows as "Sending…"; if it fails, the text goes back in the box with an explanation.
- **Sharing a lead:** "Share with a colleague" on a lead's page (staff only) opens New message with the lead attached. The composer shows it as a removable chip, and the sent message carries a card that opens the lead.
- The list checks for new messages every 30 seconds; the open conversation every 10 seconds.

The mock backend seeds four conversations and six notifications, and in the browser a colleague replies to anything you send about six seconds later — so the polling can be seen working. The data scenarios (slow, empty, error, contract) apply to all new endpoints.

## Discussion

- **Decided with Nakul (2026-09-15):** staff ↔ staff only; direct messages that can link a record (not per-record threads yet); the bell starts with approvals and assignments; build on mocks with a proposed contract and polling.
- **Proposed contracts, not agreed ones.** The backend has no notification or messaging endpoints. The schemas follow `GET /auth/me`'s conventions — a `data` envelope, snake_case, lenient optional fields — and unknown notification kinds and record types still render, so the backend can add them without a frontend release. Every schema carries `TODO(NOTIF-001)` / `TODO(MSG-001)`, and the Data IDs are registered as `mocked` with their endpoints.
- **Icons follow the contract.** The bell's icon table is typed by the known notification kinds, so adding a kind without an icon fails the type check; a kind the app doesn't know yet gets the plain bell.
- **Polling, not push.** The architecture reserves live connections for notifications and escalations, but no transport is chosen yet. Polling pauses in hidden tabs, so idle tabs cost nothing; replacing it with server-sent events or WebSockets later changes the queries, not the screens. The open conversation polls faster than the rest because a reply that takes half a minute to appear feels broken.
- **Staff-only is enforced twice:** navigation hides Messages unless the session's user type is staff (unknown counts as not staff), and the backend must return 403 to partner users — the mock does.
- **Sharing goes through the URL** (`?share=lead:…`, validated with Zod) instead of shared state, so the leads and messages features don't depend on each other's components, and a share link survives a refresh.
- **Rejected:** optimistic message bubbles in the cached thread (they need a separate "sending" shape in the cache; a "Sending…" bubble read from the pending request gives the same feedback without it); a full notifications page (not needed until there is paging).
- **Not done:** loading older messages (`nextCursor`, MSG-002); links for quotations, orders, tasks and complaints once their screens exist; read receipts and typing indicators; staging integration.

## Files changed

- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — `MSG` domain; NOTIF-001, NOTIF-002 and MSG-001 … MSG-005 registered
- `src/lib/format/date.ts`, `index.ts` — `formatTime`, `isSameDay`
- `src/lib/navigation/resource-href.ts` — which records open where, and their names
- `src/features/notifications/` — contract, API, queries, optimistic mark-as-read, the bell
- `src/features/messages/` — contract, API, queries, mutations, cache and formatting helpers, share links, conversation list, conversation, composer, message bubble, New message dialog, the Messages shell
- `src/app/(app)/messages/layout.tsx`, `page.tsx`, `[conversationId]/page.tsx` — the routes
- `src/components/layout/navigation.ts` — Messages item, staff-only items
- `src/components/layout/app-sidebar.tsx`, `command-menu.tsx`, `app-header.tsx` — unread count, staff-only navigation, the bell
- `src/features/leads/components/lead-detail.tsx` — "Share with a colleague"
- `src/mocks/data/messages.ts`, `notifications.ts`, `src/mocks/db.ts`, `src/mocks/handlers/messages.ts`, `notifications.ts`, `index.ts` — the mock backend
- `vitest.setup.ts` — no mock replies during tests
- `Docs/Frontend-Scope.md`, `Docs/Design-System.md` — scope of both features

## Tests

- `src/features/notifications/api/notifications.api.test.ts` — `[NOTIF-001]`, `[NOTIF-002]`: newest first, unread count, partners, mark one and mark all
- `src/features/notifications/lib/mark-read.test.ts` — `[NOTIF-002]`: the instant badge update
- `src/features/notifications/components/notification-bell.test.tsx` — `[NOTIF-001]`: count in the button's name, the list, mark all as read
- `src/features/messages/api/messages.api.test.ts` — `[MSG-001]` … `[MSG-005]`: order, unread totals, 403 for partners, 404, sending, linking a lead, 422 for an empty message, directory search, reusing a conversation, marking read
- `src/features/messages/lib/messages-lib.test.ts` — share links, day labels in India time, grouping, list updates
- `src/features/messages/components/conversation-thread.test.tsx` — `[MSG-002]`: shows the thread, sends with Enter, refuses an empty message
- `src/features/messages/components/messages-shell.test.tsx` — `[MSG-001]`: staff see conversations, partners see the notice
- `src/components/layout/navigation.test.ts` — `[MSG-001]`: Messages for staff only
- By hand: `npm run dev` → open the bell, click a lead notification, mark all read. Open Messages, send a message and wait for the reply, start a conversation with Imran Sheikh, share a lead from its page. Switch the role to Dealer, and try the slow, empty and error scenarios. Check 360px, a tablet and a wide screen, in light and dark.
