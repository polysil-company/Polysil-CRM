---
date: 2026-10-15
type: feature
title: Group chats
dataIds:
  - MSG-006
author: Nakul Srivastava
breaking: false
---

## Before

The backend added named groups with FS-048 (`group-chat.md`).

- Every conversation now carries `kind` and `group`, and `participant` is null for a group.
- New endpoints: `POST /conversations/groups`, `PATCH /conversations/{id}`, and the members list, add and remove.

The frontend read only one-to-one conversations. Its contract required a participant, so one group in the list would have broken the whole Messages screen.

## Now

- **The contract:** a conversation is either one to one, with its colleague, or a group, with its name, member count, manager and whether the user manages it. An older answer without `kind` reads as one to one. A group without its group, or a pair without its colleague, is a contract violation.
- **New group:** the people icon beside New message.
  - It takes a name (up to 80 characters) and colleagues ticked from the staff directory, up to 49.
  - The form names a missing name or empty list before sending.
  - The user manages the new group, and it opens at once, already listed.
- **The list mixes groups and pairs.** A group row has a group icon, its name, and its size before the last message ("4 members · Dispatch says…"). It is listed from the moment it is made.
- **A group thread** names each sender above their run of messages, from the member list, which is loaded once per thread. The header shows the name and size. The box reads "Message Saurashtra sales".
- **Group info:**
  - the members, current first, with "(you)" and "Manages this group" (from `is_manager`, so it follows a hand-over);
  - who has left;
  - **Add people**, which doesn't offer anyone already in and stops at 50 (`group_full`);
  - **Leave the group**, after a confirm.
  - The manager also renames the group and removes people.
- **Out of a group:** leaving, or a 404 while the group is open (the user was removed), says so and goes back to Messages. The group drops out of the list.
- **The mock:**
  - two groups: one the user manages with messages from three colleagues, and one someone else manages, still empty;
  - the five endpoints;
  - the rules: who may rename or remove, the hand-over to the longest-standing member, re-adding someone who left, and the 50 limit.
- Checked on a desktop in light mode and a phone in dark mode: the list, a group thread, Group info, and making a group. axe found nothing with the pointer at rest.

## Discussion

- **Stacked on #131,** which reads one conversation on its own. Merge #131 first, then retarget this PR to `integration`.
- **No Idempotency-Key handled by hand.** Like the other message calls, these writes take the key `apiRequest` adds to every mutation.
- **New group is an icon button,** named "New group" for screen readers and in its tooltip. The list's header is too narrow beside the thread for two labelled buttons.
- **Found in the walk, not changed here:** in dark mode, a hovered row with an avatar fails colour contrast. The avatar's 5% white background sits on the hover colour, and the initials fall below 4.5:1. The existing New message dialog does the same. The fix is a token change that reaches every screen, so it is noted in the plan rather than made here.
- **Not yet checked on staging.**

## Files changed

- `src/features/messages/api/messages.schemas.ts`:
  - `kind` and `group` on a conversation, with `DirectConversation`, `GroupConversation` and `conversationName`;
  - `Member`;
  - the group request and member-list schemas.
- `src/features/messages/api/messages.api.ts`: `createGroup`, `renameGroup`, `listMembers`, `addMembers`, `removeMember`.
- `src/features/messages/api/messages.queries.ts`: `groupMembersQueryOptions`, under the conversation list's key.
- `src/features/messages/api/messages.mutations.ts`: `useCreateGroup`, `useRenameGroup`, `useAddMembers`, `useRemoveMember`.
- `src/features/messages/components/people-picker.tsx`: new, the multi-select over the directory.
- `src/features/messages/components/new-group-dialog.tsx`: new.
- `src/features/messages/components/group-info-dialog.tsx`: new.
- `src/features/messages/components/conversation-list.tsx`: group rows; New group.
- `src/features/messages/components/conversation-thread.tsx`: the group header, sender names, Group info, leaving the screen.
- `src/features/messages/components/message-bubble.tsx`: `showSender`.
- `src/mocks/data/messages.ts`, `src/mocks/db.ts`, `src/mocks/handlers/messages.ts`: groups, members and the five endpoints.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: MSG-006.
- `Docs/Plan.md` (§9.1), `Docs/Tested-Features.md`, `Docs/screenshots/messages-notifications/`: records and screens.

## Tests

- `src/features/messages/api/messages.api.test.ts`, `[MSG-006] group chats`:
  - a group listed from the start, with no participant;
  - one with nobody else refused;
  - members current first, and someone who left taken back;
  - `group_full` adds nobody;
  - only the manager renames or removes, and a pair has no name (`not_a_group`);
  - leaving drops the group and hands it to the longest-standing member;
  - an older answer without `kind`, and a group without its group refused.
- `src/features/messages/components/group-chats.test.tsx`:
  - the list's group rows;
  - New group's missing fields, then made and opened;
  - a thread naming each sender;
  - Group info as manager (remove, rename) and as a member (add people, leave);
  - removed while open, back to Messages.
- `conversation-thread.test.tsx`, `messages-lib.test.ts`: brought up to the new shape.
- Walked through in the mock: desktop light and phone dark.
