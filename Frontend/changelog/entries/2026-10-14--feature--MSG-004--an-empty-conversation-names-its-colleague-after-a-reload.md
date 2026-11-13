---
date: 2026-10-14
type: feature
title: An empty conversation names its colleague after a reload
dataIds:
  - MSG-004
  - MSG-002
author: Nakul Srivastava
breaking: false
---

## Before

The backend lists a conversation only once someone writes in it, and had no way to read one on its own. So the thread named the colleague of a just-started conversation from the answer to "start", kept in the page's memory.

After a reload, or from a link a colleague shared, an empty conversation's header read "Conversation". The empty state said "No messages yet" rather than whom to write to, and the box had no name. The backend has since added `GET /conversations/{id}` (BE-021).

## Now

- **The thread reads a conversation it can't find in the list** from `GET /conversations/{id}`. That covers a conversation just started, opened after a reload, or opened from a link.
  - The header names the colleague and their role.
  - The empty state reads "Say hello to Imran Sheikh".
  - The box is labelled "Message Imran Sheikh".
- **A listed conversation is not read again;** the list, which is polled, stays the source.
- **Starting a conversation** seeds that read with the backend's answer, so the header doesn't wait for it.
- **If the read fails,** the header says "Conversation", as before, and the thread still loads and sends. A conversation that isn't the user's is a 404, and the page shows not-found, as it already did from the messages call.
- The mock answers `GET /conversations/{id}`, including the 404.
- Checked on a desktop in light mode and a phone in dark mode: a new conversation with Imran Sheikh, one read of the conversation each time. axe found nothing.

## Discussion

- **Under the list's key.** The read's query key sits under the conversation list's, so a refresh of the list (after a send, a start, or a colleague found to have left) refreshes it too.
- **Groups are not handled here.** The backend's `Conversation` now carries `kind` and `group`, with `participant` null for a group (FS-048). The frontend still expects one colleague, so a group in the list or behind a link would be a contract error. Groups are plan item 7, which widens the schema.
- **A reload can't be shown in the mock walk:** the mock's data resets on a reload, so a new conversation is gone. A unit test covers it: the conversation is started outside the page and the thread names it from the backend.

## Files changed

- `src/features/messages/api/messages.api.ts`: `getConversation`.
- `src/features/messages/api/messages.queries.ts`: `conversationQueryOptions` and `messageKeys.conversation`. They replace the in-memory `startedConversationQueryOptions`.
- `src/features/messages/api/messages.mutations.ts`: starting a conversation seeds the read.
- `src/features/messages/components/conversation-thread.tsx`: reads an unlisted conversation.
- `src/mocks/handlers/messages.ts`: `GET /conversations/:conversationId`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: MSG-004 reads one conversation.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/messages-notifications/`: records and screens.

## Tests

- `src/features/messages/api/messages.api.test.ts`, `[MSG-004]`:
  - one conversation read before anyone writes in it, and a listed one;
  - a 404 for one that isn't the user's.
- `src/features/messages/components/conversation-thread.test.tsx`, `[MSG-002] ConversationThread`:
  - the colleague named after a reload, from the backend, with the box labelled;
  - "Conversation" when the read fails, with the thread still there;
  - the existing test for a just-started conversation now seeds the read.
- Walked through in the mock: desktop light and phone dark.
