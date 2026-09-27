---
date: 2026-09-27
type: feature
title: The lead page shows its history, takes notes, moves the lead's stage and assigns it
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

The lead page showed the record and nothing else. There was no way to see what had happened to a lead — who created it, when it moved stage, why it was lost — no way to write down a call or a visit, and no way to move a lead along, lose it, reopen it or hand it to someone. The backend already served all of it (`/timeline`, `/notes`, `/transition`, `/reopen`, `/assign`, `/leads/assignees`, `/lookups/partners`).

`Docs/Plan.md` described the original delivery plan but not where the build stands, so nobody could see at a glance what runs on the real backend and what is still mocked.

## Now

**Activity on the lead page (LEAD-005, LEAD-006)** — under Details, a new **Activity** card: a note box on top, the lead's history below, newest first.

- **The history** reads as sentences with the person's name: "Asha Patel created the lead from Agri Fair", "Ravi Joshi moved the lead from Qualified to Lost" with the lost reason by name and the note, notes in a quoted block, "changed the farmer name and mobile", reopenings, assignments, merges (linking the other lead), duplicate flags, and the quotation and order events that touch the lead. Each kind has its own icon and a soft colour — green for won, red for lost, amber for reopened — never colour alone. A kind the frontend does not know yet still shows with a readable label ("Subsidy case opened"); an event is never dropped for its payload. An event whose actor is hidden from a partner reads "Polysil".
- **Paging:** the first 20 events, then **Show older activity**. If an older page fails, what is shown stays, an inline message says so, and the button becomes **Try again**.
- **States:** a skeleton that mirrors the rows; "No activity yet" when empty; an error with a copyable reference and a retry; a notice when a refresh fails but older data is on screen.
- **Adding a note:** Enter adds a line, **Ctrl/⌘ + Enter** saves (hint shown on keyboards, hidden on touch screens). The button goes Saving… → Saved, the note appears at the top of the history at once, and the box clears. A counter appears in the last 200 characters and the button disables past 2,000. A failed save keeps the text and says so; retrying the same text reuses its Idempotency-Key, so a save whose reply was lost is never added twice. The lead's last activity and score refresh after a note.
- **Who sees the note box:** anyone with `leads.edit` — never on a merged lead, which is read-only. Everyone who can see the lead sees its history.
- Works from 360px up, in light and dark, with the existing tokens only.

**Update stage (LEAD-007)** — the main button in the lead's header, for anyone with `leads.edit`.

- It offers only the moves the backend's stage machine allows from where the lead is: New → **Mark as contacted**; Contacted → **Mark as qualified**; any open lead → **Mark as lost…**; Quoted or Negotiation → **Mark as won**; Lost → **Reopen lead…**. The menu names the current stage, and a step that happens on a quotation is listed but disabled with where it happens ("Quoted — happens when a quotation is sent"), so the way forward is never a mystery. A won, merged or dormant lead shows no menu.
- **Contacted and qualified** happen at once: the button shows Updating…, a toast says "Moved to Contacted", the badge, the history, the lists and the counts update.
- **Mark as lost** asks for a reason from the administrators' list (required, "Choose why the lead was lost") and an optional note, with a red confirm button. **Mark as won** confirms and says a won lead is closed. **Reopen** takes an optional note and the toast names the stage it returned to.
- **Out of date:** every move sends the stage on screen; if someone moved the lead meanwhile, the backend refuses, the toast says "Someone moved this lead to Qualified while you had it open. It now shows the latest.", the dialog closes and the page refreshes. **Won without an accepted quotation** is explained inside the dialog: "A lead is won when a quotation on it is accepted. Accept the quotation first."
- Retrying the same move reuses its Idempotency-Key, so a lost reply never moves a lead twice.

**Assign (LEAD-008)** — an **Assign** button on the Details card, for anyone with `leads.edit`, on open leads only (the backend refuses to reassign a won, lost or merged lead).

- **Owner:** a searchable list of the people the backend says you may assign, plus **Unassigned** ("back to the office's list"). Someone who may not set owners — the backend lists nobody for them — reads "Asha Patel — only a manager can change the owner." instead of a list that would fail. A failed list says so with **Try again**.
- **Channel partner:** search partners in your area by name or code, each with its type and district, plus **No channel partner**.
- **Save** is disabled until something changes, and only what changed is sent, so the other field is never overwritten. A refused owner or partner shows on its own field ("This partner isn't in your area"); a lead that closed meanwhile closes the dialog with a toast.

**Plan (docs)** — `Docs/Plan.md` gains **§9 Integration status**: what runs on the real backend, what is still mocked and what the backend owes, what the backend serves that has no screen yet in build order, why `/leads/summary` is gone and how `/leads/stats` differs, questions for the backend, and housekeeping. A line at the top points to it. It is updated in the same pull request that connects a screen.

**Backend tasks** — `docs/Backend-Tasks.md` at the repository root lists everything the frontend needs from the backend as a checklist (BE-001…BE-014): the lead gaps (sorting, follow-up date, crops and land, win probability, territory levels, names in assignment events, stats by source), the modules still mocked (dashboard, notifications, messages), merging the tasks and complaints contracts, the dev API, a docs fix and the approval thresholds. The backend developer ticks a task, sets its status and writes the commit and notes there.

**Data IDs** — LEAD-005 (timeline), LEAD-006 (notes), LEAD-007 (stage change and reopen) and LEAD-008 (assign owner and partner) registered, in progress.

## Discussion

- **Built straight on the real contract** (`backend/docs/api/leads.md`, `api/services/leads.py`): a note is 1–2,000 characters after trimming; the timeline is keyset-paged, newest first, and folds in the events of leads merged into this one; the actor's name travels in the payload and can be empty.
- **Each event is read on its own.** The envelope (`id`, `kind`, `occurred_at`) is validated strictly and one broken event is left out and logged rather than blanking the history (`cursorPageSchema`, as the lead list does). The payload is read per kind in `lib/timeline-entries.ts`, a pure function with its own tests, so the backend adding a field or a kind never breaks the screen.
- **20 events a page**, not the backend's default 100: the first paint stays short on a phone, and most leads have fewer.
- **The stage menu mirrors the backend's rules, and the backend still decides.** `lib/lead-lifecycle.ts` copies `TRANSITIONS` from `backend/api/domain/leads.py` only to decide what to offer; every refusal code (`stage_changed`, `invalid_transition`, `stage_terminal`, `quotation_required`) has its own wording. Quoted and negotiation are never offered: the backend reaches them through a quotation (QUOT-001).
- **One-click for forward steps, a dialog for the rest.** Contacting and qualifying are frequent and low-stakes; losing, winning and reopening change what the lead is, and losing needs a reason — so those ask first.
- **Assignment sends only what changed**, following the backend's rule that a field left out is unchanged and a field sent as null is cleared. The owner list is the backend's answer, not a role check in the frontend.
- **`useIdempotencyKey`** (new, in `src/hooks`) gives one key per distinct request body; the note box, the stage menu and the dialogs share it.
- **Assignment events name no one yet.** The backend's `lead.assigned` payload carries ids only, so the history says "changed the owner" rather than "assigned to Ravi Joshi" — asked of the backend (Plan §9.4).
- **Not yet checked on the dev API by hand**: all of this is built on the backend's contract and tested against the mock, which follows its rules. Check it on the dev API before staging.
- **Next (Plan §9.3):** quotations (QUOT-001), which also move a lead to quoted, negotiation and won.

## Files changed

- `src/features/leads/api/leads.schemas.ts` — timeline, note, stage change, reopen, assignee, partner and assign contracts; the Mark lost form
- `src/features/leads/api/leads.api.ts` — `getLeadTimeline`, `addLeadNote`, `transitionLead`, `reopenLead`, `listAssignees`, `searchPartners`, `assignLead`
- `src/features/leads/api/leads.queries.ts` — the timeline (infinite, cursor-paged), assignees and partner search
- `src/features/leads/api/leads.mutations.ts` — `useAddLeadNote` (shows the note at once), `useTransitionLead`, `useReopenLead`, `useAssignLead`: the lead takes the answer, its history, the lists and the counts refresh
- `src/features/leads/lib/timeline-entries.ts` — new: what each event means, read defensively
- `src/features/leads/components/lead-timeline.tsx` — new: the history, its skeleton, paging and states
- `src/features/leads/components/lead-note-composer.tsx` — new: the note box
- `src/features/leads/lib/lead-lifecycle.ts` — new: what the stage menu offers, and what each refusal means
- `src/features/leads/components/lead-stage-menu.tsx`, `lead-stage-dialog.tsx` — new: Update stage, and the lost, won and reopen dialogs
- `src/features/leads/components/lead-assign-dialog.tsx` — new: Assign, with the owner and partner pickers
- `src/hooks/use-idempotency-key.ts` — new: one Idempotency-Key per distinct request body
- `src/features/leads/components/lead-detail.tsx` — the Activity card under Details, Update stage in the header, Assign on Details, each gated on `leads.edit`; skeleton to match
- `src/features/lookups/lib/lookup-labels.ts` — `findLookupNameById`, for the lost reason in a stage event
- `src/mocks/data/timeline.ts` — new: a history derived from each seeded lead
- `src/mocks/handlers/leads.ts`, `lookups.ts`, `src/mocks/db.ts`, `src/mocks/data/reference.ts` — timeline, notes, transition, reopen, assignees (by the previewed role), partners and assign, with the backend's stage rules, paging, 404, Idempotency-Key replay, 409 and 422; each lead's history is snapshotted once so a later change adds one event
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — LEAD-005…008
- `Docs/Plan.md` — §9 Integration status; §9.4 points to the backend task list
- `Docs/Frontend-Scope.md` — §10 points to the backend task list
- `../docs/Backend-Tasks.md` — new, at the repository root: every ask of the backend as a checklist (BE-001…BE-014) the backend developer ticks, with the commit and notes

## Tests

- `src/features/leads/lib/timeline-entries.test.ts` — `[LEAD-005]` every kind, malformed payloads, unknown kinds, merge from both sides, field names in words
- `src/features/leads/api/leads.test.ts` — `[LEAD-007]` contacted and recorded, stale view → 409 with the current stage, quoted and won-without-quotation refused, lost needs an active reason, reopen returns to the stage it was lost from, only a lost lead reopens, a retried move replayed once; `[LEAD-008]` assignees for a manager and nobody for an employee, partner search, owner and partner set and recorded, an unsent field left alone and a null one cleared, an unassignable owner on `owner_user_id`, a closed lead refused; `[LEAD-005]` newest first ending with creation, page size and cursor to older events, empty actor names kept, one broken event left out, 404; `[LEAD-006]` note becomes the newest event, retry replayed not duplicated, reused key → 409, blank note → 422 on `note`
- `src/features/leads/components/lead-activity.test.tsx` — `[LEAD-005]` skeleton then history with the lost reason by name, Show older activity, older page failing keeps what is shown, empty, error; `[LEAD-006]` save shows the note first and clears the box, Ctrl + Enter saves and Enter adds a line, a failed save keeps the text and the retry reuses the key, counter and limit; the note box for `leads.edit` only, never on a merged lead
- `src/features/leads/lib/lead-lifecycle.test.ts` — `[LEAD-007]` the moves per stage, nothing on closed leads, the quotation hints, labels, every refusal's wording and whether it is stale
- `src/features/leads/components/lead-stage.test.tsx` — `[LEAD-007]` contacted from the menu, a reason required to lose a lead, reopen with a note, someone else moved it first, won refused inside the dialog, won with an accepted quotation, no menu on a won lead or without `leads.edit`
- `src/features/leads/components/lead-assign.test.tsx` — `[LEAD-008]` owner and partner changed and shown, an employee told only a manager can change the owner, a refused partner on its field, no Assign on a closed lead
- `src/hooks/use-idempotency-key.test.ts` — one key per body, a new one after reset, stable across renders
- `src/mocks/data/timeline.test.ts` — every seeded lead's history matches the contract, runs newest first, ends lost or merged correctly, unique ids
- By hand (`npm run dev`): open a lost lead — the history ends with the reason; add a note with Ctrl + Enter; switch the scenario to Error and Slow to see those states; Update stage on a new lead → Contacted; mark it lost with a reason, then reopen it; try Mark as won on a quoted lead (refused) and on one in negotiation (won); Assign a new owner and partner as State Manager, then open Assign as Employee; switch the role to Account Manager — the history shows, but no note box, menu or Assign. Check at 360px and on a wide screen, in light and dark.
