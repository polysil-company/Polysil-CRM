# Group chats

Staff can now talk in named groups as well as one to one. A group uses the same messages, pages, read marks and unread counts. Dealers have no messages. Full contract: `docs/api/messages.md`.

## What changed on what you have

`GET /conversations` and `GET /conversations/{id}`: each conversation now has

| Field | Meaning |
|---|---|
| `kind` | `direct` or `group` |
| `participant` | the other person for `direct`; **null for a group** |
| `group` | for a group: `name`, `member_count`, `manager_id` (null only if nobody active is left), `i_manage` |

A group shows in the list from the moment it is made, with `last_message: null` until someone writes. A one-to-one conversation still shows only once written in.

Sending, reading and paging are unchanged. In a group, `participant_inactive` never happens: a member who leaves the company stays listed.

## New endpoints

| Call | What it does |
|---|---|
| `POST /conversations/groups` `{name, member_ids}` | make a group: a name of 1 to 80, and 1 to 49 colleagues. You manage it. `201` |
| `GET /conversations/{id}/members` | everyone who has been in it, current first: `person`, `added_at`, `left_at`, `is_manager`. A message carries only `sender_id`: name the sender from this list |
| `POST /conversations/{id}/members` `{user_ids}` | any member adds people. `422 group_full` past 50, and then nobody is added |
| `DELETE /conversations/{id}/members/{user_id}` | your own id: leave. Another's: the manager removes them (`403` for anyone else). `204` |
| `PATCH /conversations/{id}` `{name}` | the manager renames. `422 not_a_group` on a one-to-one conversation |

All writes take `Idempotency-Key`.

## Screens

- New group: a name, and a multi-select over `GET /staff-directory`.
- The list mixes groups and pairs. A group row shows its name and member count.
- A group thread names each sender. Load the member list once per thread.
- Group info: members, add people, leave. The manager also sees rename and remove.
- A `404` while polling a group means you are out of it: drop it from the screen.

## Rules worth knowing

- Someone who leaves sees nothing of the group. Added back, they see the whole history, and what was sent while they were out counts as unread.
- When the manager leaves, the longest-standing active member takes over. Show "manages this group" from `is_manager`, not from who created it.

## Also new: a ceiling on customer sign-in codes

Settings has a new row, `portal_otp_hourly_cap` (default 100): the most sign-in codes sent to customers in an hour. 0 sends none. The settings screen shows it with its description; nothing else to build.
