---
date: 2026-09-28
type: feature
title: "Approvals inbox: quotation discounts and sales orders, approved or
  rejected in place"
dataIds:
  - APPR-001
author: Nakul Srivastava
breaking: false
---

## Before

A discount above an officer's limit could be sent for approval (QUOT-007), but no screen let a manager decide it: the mock approved every request by itself after eight seconds. Sales orders waiting for approval had no screen either. The sidebar listed Approvals as "Soon".

## Now

**The approvals inbox (APPR-001)** — `/approvals`, in the sidebar for everyone who may see approvals, with a count of what waits on them (a dot on the collapsed rail).

- **What waits on me, oldest first:** quotation discounts and sales orders side by side. Each shows what it is, its number (or "Draft quotation"), the party, the total, the discount asked, "Indicative pricing" on stand-in rates, who raised it and when, and how long it has waited. A quotation row has **Open the quotation**; an order row says its details come with the Sales orders module.
- **Covering for a manager on leave:** **Include steps below me** (kept in the URL, `?below=true`) adds lower managers' steps, each marked whose it is ("District Manager's step"). A step nobody of its role covers always shows, marked "No District Manager to decide".
- **Approve or reject** in place. Rejecting needs a reason ("Say why — the person who asked reads it"); approving takes a remark optionally. Retrying reuses the Idempotency-Key. The request leaves the inbox, the count drops, and a decided quotation is re-read: approved, the officer's button becomes **Send**; rejected, the draft shows the reason.
- **When the request moved on** — decided by someone else, withdrawn, its draft edited after the request, an earlier step not yet decided, or not this role's step — the dialog closes, a toast says which, and the inbox shows the latest. A request you raised yourself says someone else must decide it.
- **States:** skeleton, "Nothing waits on you" (suggesting the steps below), an error, a later page failing without losing what is shown. The inbox and the count re-read every minute.
- **Permissions:** the page and count follow `approvals` in the permission list; without `approvals.approve` the rows show and the buttons don't. An Employee sees no Approvals.

**The mock** keeps a queue as the backend does: every other seeded draft above its limit waits on its manager (District up to 10 %, State 15 %, Regional 20 %), and four sales orders wait at District, State and Regional level — one stalled. A request for approval now waits here; **the eight-second auto-approval is gone**. Editing or deleting a waiting draft withdraws its request; deciding answers with the quotation or a minimal order.

## Discussion

- **One inbox for both kinds**, as the contract's Screens table asks: a manager's day is one queue. Order rows can be decided from the queue (the backend allows it); their full page comes with sales orders (SO-001), next in Plan §9.3.
- **Cards, not a table:** each row carries a decision; on a phone the buttons sit full width under the figures.
- **The remark rule:** the backend requires a remark to reject and on every Accounts decision. The Accounts role code isn't in the contract's examples, so any role naming "account" asks for one — `TODO(APPR-001)`, asked as **BE-018**.
- **Not in this slice:** the approval limits screen for admins (`GET`/`PUT /approvals/thresholds`), and deciding from the quotation page itself.
- `Docs/Plan.md` §9.3 is renumbered: sales orders next, then lead edit and merge, QR codes, tasks and the planner, complaints, then the admin screens.

## Files changed

- `src/features/approvals/` — new: `approvals.schemas.ts`, `.api.ts`, `.queries.ts`, `.mutations.ts`; `lib/approval-labels.ts` (labels, refusals, the remark rule); `components/approvals-inbox.tsx`, `approval-decision-dialog.tsx`
- `src/app/(app)/approvals/page.tsx`, `loading.tsx` — new route
- `src/components/layout/navigation.ts`, `app-sidebar.tsx` — Approvals links to the inbox, with its count
- `src/mocks/data/approvals.ts`, `src/mocks/handlers/approvals.ts` — new: the queue and the decision; `handlers/quotations.ts` — requests wait in the queue, edits and deletes withdraw them, no auto-approval; `db.ts`, `data/reference.ts`, `handlers/index.ts` — registered
- `src/features/quotations/api/quotations.lifecycle.test.ts` — approval now decided from the inbox
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — APPR-001 in progress, with its endpoints
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `../docs/Backend-Tasks.md` (BE-018), `Docs/screenshots/approvals/`
- `e2e/smoke.spec.ts` — the inbox and a reason to reject, with axe

## Tests

- `src/features/approvals/api/approvals.test.ts` — `[APPR-001]` own steps and stalled lower ones, oldest first, with the count; lower steps when asked; approving a quotation discount (it leaves the inbox, the draft may be sent); a reason to reject, then returned with it; already decided; figures changed; a sales order decided
- `src/features/approvals/components/approvals-inbox.test.tsx` — `[APPR-001]` both kinds with the count, stalled and discount; a reason required to reject, then the row leaves; approve without a remark; decided by someone else closes and refreshes; lower steps from the URL, no buttons without the permission; nothing waiting
- `src/features/quotations/api/quotations.lifecycle.test.ts` — `[QUOT-007]` approved from the inbox, then sent
- `e2e/smoke.spec.ts` — `[APPR-001]` the inbox lists requests and asks for a reason to reject; axe finds no violations
- By hand (`npm run dev`, as State Manager): open Approvals — 7 waiting; reject one without, then with a reason; approve a quotation discount and open it; tick Include steps below me; switch to Employee — no Approvals. At 360px and on a wide screen, in light and dark.
