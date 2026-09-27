---
date: 2026-09-27
type: feature
title: The lead page shows the lead's history and takes notes
dataIds:
  - LEAD-005
  - LEAD-006
  - LEAD-007
  - LEAD-008
  - MSTR-002
author: Nakul Srivastava
breaking: false
---

## Before

The lead page showed the record and nothing else. There was no way to see what had happened to a lead — who created it, when it moved stage, why it was lost — and no way to write down a call or a visit. The backend already served both (`GET /leads/{id}/timeline`, `POST /leads/{id}/notes`).

`Docs/Plan.md` described the original delivery plan but not where the build stands, so nobody could see at a glance what runs on the real backend and what is still mocked.

## Now

**Activity on the lead page (LEAD-005, LEAD-006)** — under Details, a new **Activity** card: a note box on top, the lead's history below, newest first.

- **The history** reads as sentences with the person's name: "Asha Patel created the lead from Agri Fair", "Ravi Joshi moved the lead from Qualified to Lost" with the lost reason by name and the note, notes in a quoted block, "changed the farmer name and mobile", reopenings, assignments, merges (linking the other lead), duplicate flags, and the quotation and order events that touch the lead. Each kind has its own icon and a soft colour — green for won, red for lost, amber for reopened — never colour alone. A kind the frontend does not know yet still shows with a readable label ("Subsidy case opened"); an event is never dropped for its payload. An event whose actor is hidden from a partner reads "Polysil".
- **Paging:** the first 20 events, then **Show older activity**. If an older page fails, what is shown stays, an inline message says so, and the button becomes **Try again**.
- **States:** a skeleton that mirrors the rows; "No activity yet" when empty; an error with a copyable reference and a retry; a notice when a refresh fails but older data is on screen.
- **Adding a note:** Enter adds a line, **Ctrl/⌘ + Enter** saves (hint shown on keyboards, hidden on touch screens). The button goes Saving… → Saved, the note appears at the top of the history at once, and the box clears. A counter appears in the last 200 characters and the button disables past 2,000. A failed save keeps the text and says so; retrying the same text reuses its Idempotency-Key, so a save whose reply was lost is never added twice. The lead's last activity and score refresh after a note.
- **Who sees the note box:** anyone with `leads.edit` — never on a merged lead, which is read-only. Everyone who can see the lead sees its history.
- Works from 360px up, in light and dark, with the existing tokens only.

**Plan (docs)** — `Docs/Plan.md` gains **§9 Integration status**: what runs on the real backend, what is still mocked and what the backend owes, what the backend serves that has no screen yet in build order, why `/leads/summary` is gone and how `/leads/stats` differs, questions for the backend, and housekeeping. A line at the top points to it. It is updated in the same pull request that connects a screen.

**Data IDs** — LEAD-005 (timeline) and LEAD-006 (notes) registered in progress; LEAD-007 (stage change and reopen) and LEAD-008 (assign owner and partner) registered as planned, next in line.

## Discussion

- **Built straight on the real contract** (`backend/docs/api/leads.md`, `api/services/leads.py`): a note is 1–2,000 characters after trimming; the timeline is keyset-paged, newest first, and folds in the events of leads merged into this one; the actor's name travels in the payload and can be empty.
- **Each event is read on its own.** The envelope (`id`, `kind`, `occurred_at`) is validated strictly and one broken event is left out and logged rather than blanking the history (`cursorPageSchema`, as the lead list does). The payload is read per kind in `lib/timeline-entries.ts`, a pure function with its own tests, so the backend adding a field or a kind never breaks the screen.
- **20 events a page**, not the backend's default 100: the first paint stays short on a phone, and most leads have fewer.
- **Assignment events name no one yet.** The backend's `lead.assigned` payload carries ids only, so the history says "changed the owner" rather than "assigned to Ravi Joshi". Resolving names needs `GET /leads/assignees` (LEAD-008, next) or the backend adding the names to the payload — to be asked.
- **Next:** LEAD-007 — contact, qualify, mark lost with a reason, reopen, with `expected_stage` so a stale screen gets a clear 409; LEAD-008 — assign owner and partner.

## Files changed

- `src/features/leads/api/leads.schemas.ts` — timeline event, timeline page and note contracts; `LEAD_NOTE_MAX_LENGTH`, `TIMELINE_PAGE_SIZE`
- `src/features/leads/api/leads.api.ts` — `getLeadTimeline`, `addLeadNote` with a reusable Idempotency-Key
- `src/features/leads/api/leads.queries.ts` — `leadKeys.timeline`, `leadTimelineQueryOptions` (infinite, cursor-paged)
- `src/features/leads/api/leads.mutations.ts` — `useAddLeadNote`: shows the note at once, refreshes the lead, its history and the lists
- `src/features/leads/lib/timeline-entries.ts` — new: what each event means, read defensively
- `src/features/leads/components/lead-timeline.tsx` — new: the history, its skeleton, paging and states
- `src/features/leads/components/lead-note-composer.tsx` — new: the note box
- `src/features/leads/components/lead-detail.tsx` — the Activity card under Details, gated on `leads.edit`; skeleton to match
- `src/features/lookups/lib/lookup-labels.ts` — `findLookupNameById`, for the lost reason in a stage event
- `src/mocks/data/timeline.ts` — new: a history derived from each seeded lead
- `src/mocks/handlers/leads.ts`, `src/mocks/db.ts`, `src/mocks/data/reference.ts` — timeline and notes endpoints with paging, 404, Idempotency-Key replay, 409 and 422
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — LEAD-005…008
- `Docs/Plan.md` — §9 Integration status

## Tests

- `src/features/leads/lib/timeline-entries.test.ts` — `[LEAD-005]` every kind, malformed payloads, unknown kinds, merge from both sides, field names in words
- `src/features/leads/api/leads.test.ts` — `[LEAD-005]` newest first ending with creation, page size and cursor to older events, empty actor names kept, one broken event left out, 404; `[LEAD-006]` note becomes the newest event, retry replayed not duplicated, reused key → 409, blank note → 422 on `note`
- `src/features/leads/components/lead-activity.test.tsx` — `[LEAD-005]` skeleton then history with the lost reason by name, Show older activity, older page failing keeps what is shown, empty, error; `[LEAD-006]` save shows the note first and clears the box, Ctrl + Enter saves and Enter adds a line, a failed save keeps the text and the retry reuses the key, counter and limit; the note box for `leads.edit` only, never on a merged lead
- `src/mocks/data/timeline.test.ts` — every seeded lead's history matches the contract, runs newest first, ends lost or merged correctly, unique ids
- By hand (`npm run dev`): open a lost lead — the history ends with the reason; add a note with Ctrl + Enter; switch the scenario to Error and Slow to see those states; switch the role to Account Manager — the history shows, the note box does not. Check at 360px and on a wide screen, in light and dark.
