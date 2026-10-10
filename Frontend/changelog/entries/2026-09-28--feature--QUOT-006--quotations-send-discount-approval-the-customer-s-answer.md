---
date: 2026-09-28
type: feature
title: "Quotations: send, discount approval, the customer's answer, revise and delete"
dataIds:
  - QUOT-006
  - QUOT-007
  - QUOT-008
  - QUOT-009
  - QUOT-010
  - QUOT-011
author: Nakul Srivastava
breaking: false
---

## Before

A draft could be made and edited (QUOT-004), but it stopped there: it could not be sent, a discount above the owner's limit could not be approved, the customer's answer could not be recorded, and a sent quotation could not be revised. A lead never moved to Quoted, Negotiation or Won through its quotation.

## Now

The quotation's lifecycle, on the backend's contract (`backend/docs/handover/quotations-api-contract.md` §2 and §4). A quotation's page shows only the actions its status and the user's permissions allow.

**Send (QUOT-006)** — a draft within the owner's discount limit has **Send**. The dialog offers **Send on WhatsApp** (to the party's mobile, once the PDF is ready) or **Don't send a message** (share the link by hand), and says what happens: the quotation gets its number and 45 days' validity, a qualified lead moves to Quoted, and a sent quotation is revised, not edited. A quotation on stand-in rates says the PDF carries the Indicative pricing banner. After sending, the page shows the number, "Preparing PDF…", then **Open PDF**.

**Discount approval (QUOT-007)** — a draft above the limit shows **Ask for approval** instead of Send, and a notice with the discount and the limit ("11.8% off the list price is above your limit of 5%"). The request takes an optional reason. Then the notice reads "Waiting for a State Manager to approve…", Send becomes a disabled **Waiting for approval**, and the page re-reads itself every 30 seconds. Approved: **Send** and "Discount approved" with who approved. Refused: the approver's remark and **Ask for approval** again. Void (the figures changed after approval): says so and asks again. The builder warns that saving withdraws a waiting request, or cancels a granted approval.

**The customer's answer (QUOT-008)** — **Record answer** on a sent, viewed or negotiating quotation: **Accepted…** (the lead moves to Won), **In negotiation…** (the lead moves to Negotiation), **Rejected…** (the lead does not move). Each asks for what the customer said (optional), kept on the history. Past its validity date no answer is offered, even before the nightly job marks it expired.

**Revise and versions (QUOT-009)** — **Revise** on a sent, viewed, negotiating, rejected or expired quotation makes the next version as a draft at today's prices, and opens it; any repriced line is pointed out. A **Versions** card lists every version of the number with its status, date and total, the one on screen marked; sending the new version marks the old one replaced.

**History (QUOT-010)** — a **History** card, newest first: drafted, edited, items changed, sent (on WhatsApp or by hand), opened (with the count), the answer with its remark, revised, and the discount approval's steps; older events a page at a time. The lead's history names the new quotation events too.

**Delete a draft (QUOT-011)** — for roles holding `quotations.delete`, **More actions → Delete draft…** confirms, deletes and returns to the lead. A sent quotation is never deleted.

**Refusals** — each is in words with what to do next. When someone else moved the quotation (`status_changed`, `quotation_not_draft`, `quotation_superseded`, `approval_pending`, `quotation_expired`, `predecessor_accepted`, `revision_exists`…) the dialog closes, a toast says what happened, and the page shows the latest. `rate_changed` and `no_lines` stay in the dialog with **Open the draft**; `no_approver` asks to lower the discount; `lead_not_open` says to reopen the lead.

## Discussion

- **One action bar, driven by one rule.** `quotationActions()` decides from the status, `superseded_by`, the discount's `send_gate`, the validity date and the permissions; the backend still enforces every rule. A superseded version offers nothing: its notice links to the newer one.
- **Permissions, not roles.** Send, approval, answers and revise need `quotations.edit`; delete needs `quotations.delete`, which only Admin holds in the mock.
- **Every action is idempotent**: a retry reuses its `Idempotency-Key`; a new request (after `rate_changed`, or after success) gets a new one.
- **Polling:** every 3 seconds while a PDF renders (as before), every 30 seconds while an approval waits. Both stop by themselves.
- **"Today" is India's today** (`todayInIndia()` in `lib/format`), so the validity check matches the backend's dates.
- **The mock** follows the contract's state machine and refusals and moves the lead beside the document. Two things only the mock does, so the flows can be tried end to end: a just-sent PDF is ready about 2.5 seconds later, and a request for approval is approved by a stand-in manager after 8 seconds, because the approvals inbox (APPR-001) is not built yet. Mock approvers: District 10%, State 15%, Regional 20%; above that, `no_approver`.
- **Asked of the backend** (`docs/Backend-Tasks.md`): BE-017, put `quotation_id`, `quote_no` and `version` on quotation events in the lead's timeline, so the lead's history can say which quotation.
- **Next:** the public `/q/{token}` page (QUOT-012), then the approvals inbox's quotation rows with APPR-001.

## Files changed

- `src/features/quotations/api/quotations.schemas.ts` — send gates and approval statuses as enums; the approval request on the document; the send, approval, answer, revise and delete requests; versions; the remark form
- `src/features/quotations/api/quotations.api.ts`, `quotations.queries.ts`, `quotations.mutations.ts` — `sendQuotation`, `requestQuotationApproval`, `transitionQuotation`, `reviseQuotation`, `listQuotationVersions`, `getQuotationTimeline`, `deleteQuotation`; versions and history queries; one mutation each, refreshing the document, lists, versions, history and the lead; polling while an approval waits
- `src/features/quotations/lib/quotation-lifecycle.ts` — new: the actions a quotation offers, the send step by `send_gate`, the draft's discount notice, refusals in words, history lines
- `src/features/quotations/components/` — new: `QuotationActions`, `QuotationActionDialog` (send, approval, answer, revise, delete), `QuotationVersions`, `QuotationHistory`; `QuotationDetail` — the action bar, the discount notice, the Versions and History cards; `QuotationBuilder` — the warning before saving over an approval
- `src/features/leads/lib/timeline-entries.ts` — labels for the new quotation events on a lead's history
- `src/lib/format/date.ts` — `todayInIndia()`
- `src/mocks/handlers/quotations.ts` — the lifecycle endpoints; saves cancel an approval and keep a revision's version; history per quotation; `src/mocks/handlers/lead-events.ts` — new: the lead-event writer, now shared with quotations; `src/mocks/data/quotations.ts` — `withLines`, the seeded drafts' real discount; `src/mocks/db.ts` — history, PDF and approval timers, delete replays
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — QUOT-006…011
- `Docs/Plan.md` — §9: the lifecycle connected
- `../docs/Backend-Tasks.md` — BE-017

## Tests

- `src/features/quotations/lib/quotation-lifecycle.test.ts` — `[QUOT-006]` the send step for each gate, refusals marked stale or kept; `[QUOT-008]` the actions for a draft, a sent, negotiating, rejected, expired, accepted, lapsed and superseded quotation, and without permissions; `[QUOT-007]` the discount notice for each gate with the approver's role and remark; `[QUOT-010]` history lines, unknown and odd events
- `src/features/quotations/api/quotations.lifecycle.test.ts` — `[QUOT-006]` a send numbers, links and moves the lead; `discount_approval_required`, `no_lines`; `[QUOT-007]` a request to the right manager, `approval_pending`, then sent once approved; `approval_not_required`, `no_approver`; `[QUOT-008]` negotiation then acceptance wins the lead; `status_changed`, `invalid_transition`; `[QUOT-009]` version 2 of the same number supersedes version 1 once sent, `revision_exists`, no revising a draft; `[QUOT-010]` history newest first; `[QUOT-011]` delete and replay, never a sent one
- `src/features/quotations/components/quotation-actions.test.tsx` — `[QUOT-006]` send without a message and see the number; a stale refusal closes the dialog; `[QUOT-007]` ask for approval, then wait; `[QUOT-008]` mark accepted; `[QUOT-009]` revise opens version 2; `[QUOT-011]` delete as Admin returns to the lead, no delete for a State Manager
- `src/lib/format/format.test.ts` — `todayInIndia()` across midnight in India
- By hand (`npm run dev`, role Admin): open a draft above the limit → Ask for approval → wait for "Discount approved" → Send → Open PDF once ready → Record answer → In negotiation → Revise → the new draft with Versions → More actions → Delete draft. At 360px and on a wide screen, in light and dark.
