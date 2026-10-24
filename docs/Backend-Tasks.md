# Backend tasks — asked by the frontend

The one place the frontend track writes down what it needs from the backend, and where the backend
track marks it done. Everything the frontend is waiting on is here; nothing lives only in a chat.

**Where it lives:** `docs/Backend-Tasks.md` on `integration`. Pull `integration`, work from it, and
update this file in the same pull request as the change.

## How to update a task

1. Tick its box in the **checklist** and change its **Status** in the details below.
2. Fill in **Done in** — the commit or pull request (`a1b2c3d`, `#21`).
3. Write what the frontend needs to know under **Backend notes**: the decision, the field names,
   anything that works differently from the ask. "Won't do" and "answered differently" are fine —
   say why.
4. Regenerate `backend/docs/api/*.md` if an endpoint changed, as usual.

The frontend reads this file after every merge into `integration` and picks up what is done.

**Status:** ⬜ Open · 🟡 In progress · ✅ Done · 💬 Answered (a decision, no code) · ❌ Won't do

**Adding a task (frontend):** the next free `BE-` number, a line in the checklist, and a details block
in the same shape. Never renumber or reuse a number.

---


> **From the backend, after the staging walk:** the frontend's open items (approve or return a discount, an Approvals link in the sidebar, the new name fields in the lead history, "Awaiting approval" in the quotation list) are in `backend/docs/handover/frontend-walk-findings.md`.

## Checklist

**Leads**

- [x] **BE-001** · Sorting on `GET /leads` · LEAD-001 · normal
- [x] **BE-002** · A next follow-up date on a lead · LEAD-001, LEAD-003, RPT-001 · high
- [x] **BE-003** · Crops and land (acres) on a lead · LEAD-003 · normal
- [x] **BE-004** · Win probability and weekly activity — or confirm they are replaced · LEAD-001, LEAD-003 · low
- [x] **BE-005** · Which territory levels a lead may sit in · LEAD-002 · normal
- [x] **BE-006** · Names in the `lead.assigned` timeline payload · LEAD-005 · low
- [x] **BE-007** · Lead counts by source and by inquiry type on `GET /leads/stats` · LEAD-004, RPT-001 · normal

**Modules the frontend still mocks**

- [x] **BE-008** · Dashboard figures · RPT-001 · high
- [x] **BE-009** · In-app notifications · NOTIF-001, NOTIF-002 · high
- [x] **BE-010** · Staff messages · MSG-001…MSG-005 · normal

**Repository and environments**

- [x] **BE-011** · Merge the tasks (FS-014) and complaints (FS-015) contracts into `integration` · TASK-001, CMPL-001 · normal
- [x] **BE-012** · Keep the dev API on the latest `integration`, and share the test password · OBS-002 · high
- [x] **BE-013** · Fix the pagination row in the API docs' conventions · OBS-002 · low
- [x] **BE-014** · Approval threshold amounts per role · APPR-001 · normal

**Quotations** — added as the quotation screens are built (QUOT-001…).

- [x] **BE-015** · Point quotation share links at the app: set `PUBLIC_WEB_URL` · QUOT-002 · high
- [x] **BE-016** · Say whether the dev API renders real PDFs · QUOT-003 · normal
- [x] **BE-017** · Name the quotation on its events in the lead's timeline · QUOT-010 · normal

**Approvals** — added as the approval screens are built (APPR-001…).

- [x] **BE-018** · Name the Accounts role code in the approval queue · APPR-001 · normal

**Sales orders** — added as the order screens are built (SO-001…, DISP-002).

- [x] **BE-019** · Find the order that carries a quotation: a `quotation_id` filter on `GET /orders` · SO-003 · low
- [x] **BE-020** · Name the order on its events in the lead's timeline · SO-002, LEAD-005 · normal
- [x] **BE-029** · List only the quotations still free to order: an `orderable` filter on `GET /quotations` · SO-011 · low

**Messages** — added as the message screens are connected (MSG-001…).

- [x] **BE-021** · Read one conversation: `GET /conversations/{id}` · MSG-002, MSG-004 · low

**Operations queues** — added as the Dispatch and Accounts screens are built (DISP-001, ACCT-001).

- [x] **BE-022** · An Accounts queue: orders waiting on the payment check, and what Accounts records · ACCT-001 · normal

**Subsidy** — added as the application screens are built (SUBS-004…).

- [x] **BE-023** · Find a lead's subsidy application: a `lead_id` filter on `GET /subsidy-applications` · SUBS-005 · normal

**Product master** — added as the catalogue and price-list screens are built (MSTR-004…006).

- [x] **BE-024** · List the product categories and units: `GET /lookups/product-categories`, `GET /lookups/uoms` · MSTR-004 · normal

**Documents** — added as the documents on records are built (DOC-001…003).

- [x] **BE-025** · Offer only the document types a record takes: `record_type` on `GET /documents/types` · DOC-002 · low

**Masters** — added as Admin → Masters is built (MSTR-009, MSTR-010).

- [x] **BE-026** · Show a list row's sort order, quality and kind: return them on `LookupItem` · MSTR-009 · low

**Schemes** — added as the schemes are built (SCHM-001…004).

- [x] **BE-027** · Name a scheme's targets, and list product categories with their ids · SCHM-001, SCHM-002 · normal

**Marketing material** — added as it is built (MKT-002…004).

- [x] **BE-028** · Say which roles may order, approve and send marketing material: default grants for `marketing_material` · MKT-002, MKT-003, MKT-004 · normal

**Partner portal** — added from the dealer portal walk (item 38).

- [x] **BE-030** · Say on `GET /auth/me` whether tasks are on for dealers (`tasks_for_dealers`) · TASK-009, AUTH-002 · low

**Complaints** — added as the complaint screens grow (CMPL-013).

- [ ] **BE-031** · A complaint's PDF, like a quotation's or an order's: `pdf_state` and `GET /complaints/{id}/pdf` · CMPL-013 · normal

**Field tracking app** — added for the Android tracking app (TRK-008).

- [ ] **BE-032** · A device token for the tracking app, so points upload while the app is closed · TRK-008 · high

**Leads** — added with the Deleted leads list (LEAD-019).

- [ ] **BE-033** · Restore a deleted lead, and say when and by whom it was deleted · LEAD-019, LEAD-011 · normal

**From the live test of 22–23 Oct** (`Frontend/Docs/Live-Test-Report.md`, PR #200).

- [ ] **BE-034** · Redeploy the API on the test box from `integration`: none of BE-023 to BE-030 is live · APP-009 · high
- [ ] **BE-035** · Refuse a quotation with no items (`POST /quotations`, and sending an empty draft) · QUOT-004, QUOT-006 · normal
- [ ] **BE-036** · The dashboard's overdue follow-ups say 0 while Tasks shows 1 overdue · RPT-001, TASK-001 · normal
- [ ] **BE-037** · Decide: may a state manager delete leads? The test box grants it; RBAC.md and the mock don't · LEAD-011, LEAD-019 · normal
- [ ] **BE-038** · Decide: may a dispatch take a warehouse's stock below zero? · DISP-002, MSTR-015 · normal

**Dealers and their employees** — the client's ask of 24 Oct. The questions are in the client document *Polysil CRM — Employees on dealers* (24 Oct); each item says whether it can start before the answers.

- [ ] **BE-039** · A quotation for a dealer or distributor, with no farmer's lead · QUOT-004, QUOT-006 · high · **can start now**
- [ ] **BE-040** · The employee(s) who look after a dealer or distributor · CHNL-001 · high · **the link can start now; what it grants waits on the client**
- [ ] **BE-041** · An employee's leads go to their dealer when the employee leaves · ADMN-004, LEAD-008 · normal · **waits on the client**

---

## Details

### BE-001 · Sorting on `GET /leads`

- **Status:** ✅ Done
- **Asked:** 22 Sep 2026 · LEAD-001 · Frontend-Scope §10 question 14
- **What:** accept `sort` = `created_at` | `farmer_name` | `estimated_value` and `order` = `asc` |
  `desc` on `GET /leads`, keeping keyset paging (the cursor carries the sort key).
- **Why:** the lead table's sort arrows already send these; today the list is always newest first,
  so clicking Customer or Value does nothing.
- **Done when:** the list comes back in the asked order, page after page, with no gaps or repeats.
- **Done in:** #30
- **Backend notes:** `GET /leads` takes `sort` = `created_at` | `farmer_name` | `estimated_value` and `order` = `asc` | `desc` (default `created_at`, `desc`).
  - `farmer_name` ignores case.
  - A lead with no `estimated_value` comes last in both orders.
  - Ties break by id, so pages never repeat or skip a row.
  - The cursor remembers its sort: sending it with a different `sort` or `order` is `422` on `cursor`, so reset the cursor when the user changes the sort.
  - The old cursor form keeps working for the default order.
  - Spec: `backend/docs/specs` is internal; the contract is `backend/docs/api/leads.md`.

### BE-002 · A next follow-up date on a lead

- **Status:** 💬 Answered
- **Asked:** 22 Sep 2026 · LEAD-001, LEAD-003, RPT-001 · Frontend-Scope §10 question 15
- **What:** a `next_follow_up_at` (ISO date-time, nullable) on `Lead`, settable when a note is added
  or by a small `PATCH`, and a filter `follow_up_due=today|overdue` on `GET /leads`.
- **Why:** the Follow-up column and field show "—"; the dashboard's "overdue follow-ups" figure and
  list cannot be real without it.
- **Done when:** a lead carries the date, it can be set and cleared, and the list can filter on it.
- **Done in:** #25 (merged into `integration` 28 Sep 2026)
- **Backend notes:** Follow-ups are **tasks**, not a field on the lead. A lead's own follow-ups are `GET /tasks?lead_id=`; `GET /leads/stats` counts `follow_ups_due_today` and `follow_ups_overdue` from open tasks (null for dealers). Contract: `backend/docs/handover/tasks-and-planner-contract.md`. _Recorded by the frontend from #25's description._

### BE-003 · Crops and land (acres) on a lead

- **Status:** ✅ Done
- **Asked:** 22 Sep 2026 · LEAD-003 · Frontend-Scope §10 question 16
- **What:** `crops` (codes from an admin list, several) and `land_acres` (decimal string, nullable)
  on `Lead`, in create and `PATCH`.
- **Why:** captured on field visits; the lead page shows "—" for both.
- **Done when:** both are on `Lead`, in `LeadCreate` and `LeadPatch`, with a `GET /lookups/crops`
  list (or say which existing list to use — `GET /subsidy/crops`?).
- **Done in:** #30
- **Backend notes:** `crops` and `land_acres` on `Lead`, `LeadCreate` and `LeadPatch`.
  - In a request, `crops` is a list of codes from the new `GET /lookups/crops` (78 crops, from the subsidy workbooks' list). At most 10. `[]` clears it; `null` is refused.
  - In `Lead`, each crop is `{ code, name, is_active }`, in the order sent.
  - A crop switched off later stays on the leads that have it (`is_active: false`, show it greyed). It may be re-sent with the record, but not added to a lead that lacks it.
  - `land_acres` is a decimal string: more than 0, at most 99999.99, two decimals; `null` clears it.
  - Admins add or switch off crops with `POST /lookups/crops` and `PATCH /lookups/crops/{id}` (`masters.edit`), like the other lead lists.
  - Not `GET /subsidy/crops`: that one is gated on `subsidy.view`, which dealers lack.

### BE-004 · Win probability and weekly activity — or confirm they are replaced

- **Status:** 💬 Answered
- **Asked:** 22 Sep 2026 · LEAD-001, LEAD-003 · Frontend-Scope §10 question 17
- **What:** either a `win_probability` (0–100) and a weekly interaction count on `Lead`, or a
  decision that `score` replaces win probability and the timeline replaces weekly activity.
- **Why:** the lead page has two cards and the table two columns that show "—". A decision is
  enough — the frontend removes them.
- **Done when:** decided (💬 is fine), with the fields if they stay.
- **Done in:** —
- **Backend notes:** No new fields. `score` (0 to 100) and `priority` (hot, warm, cold) replace win probability. The lead timeline replaces weekly activity. Remove the two cards and the two columns.

### BE-005 · Which territory levels a lead may sit in

- **Status:** ✅ Done
- **Asked:** 22 Sep 2026 · LEAD-002 · Frontend-Scope §10 question 18
- **What:** the docs say a lead sits in a taluka or district, but `GET /lookups/territories` also
  returns villages and the state. Either refuse the other levels on `POST /leads`, or filter them
  out of the search (a `levels=district,taluka` parameter would do).
- **Why:** the New lead form's territory picker offers what the search returns.
- **Done when:** the rule is decided and enforced in one place.
- **Done in:** #30
- **Backend notes:** A lead may sit in a **district, a taluka or a village**. A state is refused: `422` on `territory_id`.
  - Call `GET /lookups/territories?levels=district,taluka,village` for the New lead picker. `levels` is comma-separated; with `level` too, or with an unknown level, it is `422` on `levels`.
  - On `PATCH` the level is checked only when `territory_id` changes, so re-sending the whole record is fine.
  - Villages stay allowed because the seed and many existing leads use them; the client may narrow it later.
  - The public lead form stays at district or taluka, as before. A QR code's territory now refuses a state too.

### BE-006 · Names in the `lead.assigned` timeline payload

- **Status:** ✅ Done
- **Asked:** 27 Sep 2026 · LEAD-005, LEAD-008
- **What:** add `owner_name` and `partner_name` next to `owner_user_id` and `assigned_partner_id`
  in the `lead.assigned` event's payload, as `actor_name` already is.
- **Why:** the lead's history can only say "changed the owner", not "assigned to Ravi Joshi": the
  payload carries ids, and most people cannot look users up.
- **Done when:** new `lead.assigned` events carry both names (null when cleared). Old events can
  stay as they are.
- **Done in:** #30
- **Backend notes:** Every `lead.assigned` event on `GET /leads/{id}/timeline` now carries a name key beside each person id: `owner_user_id` → `owner_name`, `assigned_partner_id` → `partner_name`, and on a handover `previous_owner_user_id` → `previous_owner_name`.
  - A name key is present whenever its id key is; null when the id is null (cleared).
  - Added when the timeline is read, so old events have them too.

### BE-007 · Lead counts by source and by inquiry type on `GET /leads/stats`

- **Status:** ✅ Done
- **Asked:** 27 Sep 2026 · LEAD-004, RPT-001
- **What:** `by_source` (source code → count) and `by_inquiry_type` (type → count) in `LeadStats`,
  over the same scope and filters as today.
- **Why:** the old guessed `/leads/summary` had them and the dashboard's "Leads by source" chart
  needs them. With these, the dashboard can use `/leads/stats` instead of a mock for that chart.
- **Done when:** both maps are present, every known code included with 0 when empty.
- **Done in:** #25 (merged into `integration` 28 Sep 2026)
- **Backend notes:** `GET /leads/stats` gains `by_source`, `by_inquiry_type`, `follow_ups_due_today` and `follow_ups_overdue` (the last two null for dealers). _Recorded by the frontend from #25's description._

### BE-008 · Dashboard figures

- **Status:** ✅ Done
- **Asked:** 27 Sep 2026 · RPT-001
- **What:** the dashboard is mocked as `GET /dashboard/overview` —
  `Frontend/src/features/dashboard/api/dashboard.schemas.ts` is the shape it draws:
  - `kpis` — pipeline value, new leads, conversion rate, overdue follow-ups; each with `value`,
    `delta_percent` against the previous period and a short `trend` series
  - `pipeline` — count and value per stage
  - `sources` — lead count per source
  - `follow_ups` — the next due follow-ups: lead, farmer, district, due at, owner
- **Why:** the first screen after sign-in shows invented numbers.
- **Done when:** either that endpoint (field names in snake_case are fine; the frontend adapts), or
  agreement that the dashboard composes `GET /leads/stats` (with BE-007), `GET /orders/stats` and a
  follow-up list (needs BE-002). Write which in the notes.
- **Done in:** #30
- **Backend notes:** `GET /dashboard/overview?days=7|30|90` (default 30), in the mock's shape, snake_case.
  - `kpis`: `pipeline_value`, `new_leads`, `conversion_rate` and `overdue_follow_ups`.
    - Each has `value`, `delta_percent` and `trend`, all decimal strings.
    - `pipeline_value` and `overdue_follow_ups` are snapshots of now: `delta_percent` is null and `trend` is empty.
    - `overdue_follow_ups.value` is null for a dealer.
  - `pipeline`: count and value per stage.
  - `sources`: leads per source in the period.
  - `follow_ups`: the next 10 open tasks on your leads, with `district`, `assigned_to` and `overdue`.
  - Every figure is in the caller's scope. A role with no lead permission gets zeros, never a 403.
  - Our definitions, to confirm with the client: conversion is the share of the period's new leads won now; pipeline value counts new to negotiation.
  - Contract: `backend/docs/api/dashboard.md`.

### BE-009 · In-app notifications

- **Status:** ✅ Done
- **Asked:** 27 Sep 2026 · NOTIF-001, NOTIF-002
- **What:** `GET /notifications` (newest first, with the unread count) and `POST /notifications/read`
  (some ids, or all). The mocked shape is in
  `Frontend/src/features/notifications/api/notifications.schemas.ts`.
- **Why:** the bell in the top bar runs on the mock.
- **Done when:** both endpoints exist in the caller's scope; say which events create notifications.
- **Done in:** #31
- **Backend notes:** `GET /notifications?limit=&cursor=&unread=true` and `POST /notifications/read` with `{ "ids": [...] }` or `{ "all": true }`, in your proposed shape.
  - `meta.unread_count` counts all unread, not only the page.
  - Each notification has `kind`, `title`, `body`, `actor`, `resource {type, id, label}`, `created_at` and `read_at`.
  - Kinds:
    - `lead_assigned`, `task_assigned`, `lead_note`;
    - `approval_requested`, `complaint_to_check`, `complaint_to_qc`, `complaint_assigned`;
    - `order_approved`, `order_returned`, `discount_approved`, `discount_returned`;
    - `complaint_returned`, `complaint_qc_approved`, `complaint_qc_rejected`.
  - Nobody is notified of their own action. A dealer is never told who decided: `actor` is null for them on a decision.
  - No push: poll `?limit=1` for the count.
  - Contract: `backend/docs/api/notifications.md`.

### BE-010 · Staff messages

- **Status:** ✅ Done
- **Asked:** 27 Sep 2026 · MSG-001…MSG-005
- **What:** conversations between staff, as mocked in
  `Frontend/src/features/messages/api/messages.schemas.ts`:
  - `GET /conversations` — with unread counts
  - `GET /conversations/{id}/messages` and `POST /conversations/{id}/messages` — a message may link a
    CRM record (a lead today)
  - `POST /conversations` — start one; `POST /conversations/{id}/read`
  - `GET /staff-directory` — search staff to message
- **Why:** Messages runs on the mock; "Share with a colleague" on a lead depends on it.
- **Done when:** the endpoints exist, or a decision to drop or defer the module.
- **Done in:** #31
- **Backend notes:** One-to-one staff conversations, in your proposed shape.
  - Endpoints:
    - `GET /staff-directory?q=`;
    - `GET /conversations` (with `meta.unread_total`);
    - `POST /conversations` with `{ "participant_id" }` (`201` new, `200` existing);
    - `GET /conversations/{id}/messages` (oldest first, `meta.next_cursor` for older);
    - `POST /conversations/{id}/messages` with `{ "body", "resource": { "type": "lead", "id" } | null }`;
    - `POST /conversations/{id}/read`.
  - **Mark read with `{ "up_to": "<newest message id on screen>" }`.** A message arriving meanwhile then stays unread. Leave it out only for "mark all read" from the inbox.
  - `participant.is_active` is false for a colleague who has left. The history stays readable; a new message is `422 participant_inactive`.
  - A lead link must be a lead the sender can see. The backend fills the label with its inquiry number.
  - Dealers get `403` everywhere. No push: poll.
  - Contract: `backend/docs/api/messages.md`.

### BE-011 · Merge the tasks and complaints contracts into `integration`

- **Status:** ✅ Done
- **Asked:** 27 Sep 2026 · TASK-001, CMPL-001
- **What:** `backend-foundation` has two commits `integration` does not: "Tasks and planner
  contract (FS-014)" and "Complaints contract for the frontend track (FS-015)".
- **Why:** the frontend builds from `integration`; those contracts are not visible there yet.
- **Done when:** merged into `integration`.
- **Done in:** #25 (merged into `integration` 28 Sep 2026)
- **Backend notes:** Tasks and the planner (`/tasks`, `/planner`, `/planner/team`, `/minutes`, `/lookups/meeting-types`) and complaints to the quality check (`/complaints`, `/complaint-sla-policies`, `/lookups/complaint-types`) are on `integration`. Contracts: `backend/docs/handover/tasks-and-planner-contract.md`, `complaints-contract.md`. _Recorded by the frontend from #25's description._

### BE-012 · Keep the dev API on the latest `integration`, and share the test password

- **Status:** 💬 Answered
- **Asked:** 27 Sep 2026 · OBS-002
- **What:** deploy `https://polysil-api.pranayx.tech` from the latest `integration` after each
  backend merge, and share the test accounts' password with the frontend developer (not in the
  repository — `backend/docs/handover/dev-api-access.md` says to ask).
- **Why:** lead history, notes, stage changes and assignment (LEAD-005…008) are built on the
  contract and tested against the mock, but not yet checked by hand on the dev API.
- **Done when:** the dev API runs the latest `integration`, and the frontend has the password.
- **Done in:** —
- **Backend notes:** The dev API (`https://polysil-api.pranayx.tech`) is deployed from the same code that goes into `integration`, after each backend merge. The test password is shared directly, not in the repository.

### BE-013 · Fix the pagination row in the API docs' conventions

- **Status:** ✅ Done
- **Asked:** 27 Sep 2026 · OBS-002
- **What:** `backend/docs/api/README.md` says "Pagination: `page`, `limit`, `sort`, `q`", but the
  lists page by cursor (`limit`, `cursor`, `meta.next_cursor`, `include_total`).
- **Why:** the README is the first thing anyone reads; it sent the frontend down page numbers once.
- **Done when:** the generator writes the cursor convention.
- **Done in:** #30
- **Backend notes:** The conventions table in `backend/docs/api/README.md` now says: paging by cursor, `limit`, `meta.next_cursor` → `cursor`, and `include_total=true` for a capped `meta.total`.

### BE-014 · Approval threshold amounts per role

- **Status:** ✅ Done
- **Asked:** 21 Sep 2026 · APPR-001 · Frontend-Scope §10 question 7
- **What:** the real discount and order-value limits per role — the seed has stand-in thresholds.
- **Why:** quotation discount approval and order approval depend on them; the screens show the
  backend's answer, but the demo should use the client's numbers.
- **Done when:** the client's figures are in the seed or configured, or the notes say who owes them.
- **Done in:** #75
- **Backend notes:** Nothing to build: `GET /approvals/thresholds` and `PUT` (Admin) already set the order and discount limits per role (`backend/docs/api/approvals.md`). The seed figures are stand-ins (1,00,000 and 5,00,000); the client owes the real ones, question 15.1, GAP-122. Handover: `backend/docs/handover/accounts-queue-order-names.md`.

### BE-015 · Point quotation share links at the app: set `PUBLIC_WEB_URL`

- **Status:** ✅ Done
- **Asked:** 27 Sep 2026 · QUOT-002, QUOT-003
- **What:** set `PUBLIC_WEB_URL` on the dev API (and later staging) to the frontend's origin for that
  environment. It defaults to `http://localhost:3000`, and `share_url` on every sent quotation is built
  from it.
- **Why:** the quotation page shows the customer link with a Copy button, and the WhatsApp message
  carries it. With the default, every link sent from the dev API points at localhost. The public page
  `/q/{token}` is being built on the frontend (QUOT, a later slice).
- **Done when:** a quotation sent on the dev API has a `share_url` on the frontend's dev origin. Write
  the origin in the notes.
- **Done in:** the dev API's configuration
- **Backend notes:** `PUBLIC_WEB_URL` is `https://polysil.pranayx.tech` on the dev API, so `share_url` points at the frontend.

### BE-016 · Say whether the dev API renders real PDFs

- **Status:** 💬 Answered
- **Asked:** 27 Sep 2026 · QUOT-003
- **What:** `pdf_renderer` can be `html` on a box without WeasyPrint, storing the rendered HTML as the
  document. Say which the dev API uses, and switch it to `weasyprint` if it can.
- **Why:** **Open PDF** opens the signed link in a new tab; if the dev API serves HTML, what the
  frontend developer checks there is not what the farmer receives.
- **Done when:** decided and noted (💬 is fine).
- **Done in:** —
- **Backend notes:** The dev API renders real PDFs with WeasyPrint (`pdf_renderer` must be `weasyprint` outside a local box; the API refuses to start otherwise). PDFs still fail on the dev API until its file storage (R2) is configured: until then a sent quotation shows its render error.

### BE-017 · Name the quotation on its events in the lead's timeline

- **Status:** ✅ Done
- **Asked:** 28 Sep 2026 · QUOT-010, LEAD-005
- **What:** on every `quotation.*` event that `GET /leads/{id}/timeline` returns, add `quotation_id`,
  `quote_no` (null on a draft) and `version` to the payload. The contract lists `from`, `to`, `remark`
  and `actor_name` only.
- **Why:** a lead's history shows "Quotation sent", "Quotation accepted" and so on, but cannot say
  which quotation or link to it when a lead has more than one (a revision, or a second unit).
- **Done when:** the payloads carry the three fields; say in the notes if a dealer should not see
  any of them.
- **Done in:** #30
- **Backend notes:** Every `quotation.*` event on `GET /leads/{id}/timeline` now carries `quotation_id`, `quote_no` (null on a draft) and `version`.
  - Always present on the quotation events that reach the reader: the timeline already hides a quotation the reader cannot see.
  - A dealer sees all three on the events it sees; they are on a quotation the dealer can already open.
  - Added when read, so old events have them too.

### BE-018 · Name the Accounts role code in the approval queue

- **Status:** 💬 Answered
- **Asked:** 28 Sep 2026 · APPR-001
- **What:** say which `role` value a `GET /approvals/pending` row carries for an Accounts step (and
  for QA and Dispatch, if they appear there), and confirm that a remark is required on every
  Accounts decision, approve included.
- **Why:** the decision dialog asks for a remark when the backend will require one. Today it treats
  any role containing "account" as Accounts (`TODO(APPR-001)` in
  `Frontend/src/features/approvals/lib/approval-labels.ts`), and the role's name on screen comes
  from the frontend's role list — an unknown code shows humanised.
- **Done when:** the codes are in the notes (or `backend/docs/api/approvals.md`).
- **Done in:** —
- **Backend notes:** `GET /approvals/pending` rows carry the role **code** in `role`:
  - order steps: `district_manager`, `state_manager`, `regional_manager`, then `account_manager` (Accounts) and `dispatch_manager` (Dispatch);
  - quotation discount steps: `district_manager`, `state_manager`, `regional_manager`, `admin_sales`.
  - QA (`qc_manager`) never appears there: complaints have their own queue, `GET /complaints?awaiting=me`.
  - `decided_role` is set when a higher manager decided a step in place of its own role.
  - A remark is required on every `reject`, and on **every** Accounts decision, approve included.

### BE-019 · Find the order that carries a quotation: a `quotation_id` filter on `GET /orders`

- **Status:** ✅ Done
- **Asked:** 29 Sep 2026 · SO-003
- **What:** accept `quotation_id` on `GET /orders` (orders whose `quotations` include it), or add
  `quotation_ids` to `OrderSummary`.
- **Why:** an accepted quotation's page offers "Place order", or "Open order" when a live order
  already carries it — `POST /orders` answers `409 quotation_on_order` otherwise. The list rows
  carry no quotation ids, so today the page lists the lead's orders and reads each live one
  (up to ten) to find the match. One filtered call would do.
- **Done when:** `GET /orders?quotation_id=…` returns the order(s) carrying that quotation, in the
  caller's scope.
- **Done in:** #36 (commit c284913)
- **Backend notes:** `quotation_id` on `GET /orders` lists the orders this quotation is or was on.
  A cancelled order released it, so add `status` to find the live one
  (`backend/docs/api/orders.md`). Ticked by the frontend after reading the contract; the
  frontend uses it since the backend pick-ups pull request (`place-order.tsx`).

### BE-020 · Name the order on its events in the lead's timeline

- **Status:** ✅ Done
- **Asked:** 2 Oct 2026 · SO-002, LEAD-005 (demo walk, D-6)
- **What:** on every `order.*` and `dispatch.*` event that `GET /leads/{id}/timeline` returns, add
  `order_id` and `order_no` (null on a never-submitted draft) to the payload, as BE-017 did for
  quotations (`quotation_id`, `quote_no`, `version`). Several of these events carry `{}` today
  (`order.approved`, `order.returned`, `order.closed_short`, `order.deleted`).
- **Why:** the lead's history says "Sales order submitted" or "Dispatch recorded" but cannot
  say which order or link to it. The frontend already reads `order_id` and `order_no` when they
  are there (`timeline-entries.ts`), so nothing else changes on its side.
- **Done when:** the order events on a lead's timeline carry both fields, added when read so old
  events have them too.
- **Done in:** #75
- **Backend notes:** Every event about an order on the lead timeline (`order.*`, `dispatch.*`, `approval.decided`, `payment.*`) carries `order_id` and `order_no`, added when read so old events have them too. `order_no` is null until submitted.

### BE-021 · Read one conversation: `GET /conversations/{id}`

- **Status:** ✅ Done
- **Asked:** 2 Oct 2026 · MSG-002, MSG-004
- **What:** `GET /conversations/{conversation_id}` answering the `Conversation` (participant,
  last message, unread count), `404` when it is not the caller's. Or: list a conversation the
  caller opened even before anyone writes in it.
- **Why:** a new conversation is not listed until someone writes in it, and nothing else reads
  one. The thread names the colleague from the `POST /conversations` answer, but after a reload,
  or from a shared link, an empty conversation's header can only say "Conversation" and the box
  cannot say whom it writes to.
- **Done when:** the thread can name the colleague of any conversation the caller is in, written
  in or not.
- **Done in:** #75
- **Backend notes:** `GET /conversations/{conversation_id}` answers the `Conversation`, written in or not. `404` when it is not yours, `422` for a bad id, `403` for a dealer.

### BE-022 · An Accounts queue: orders waiting on the payment check, and what Accounts records

- **Status:** ✅ Done
- **Asked:** 4 Oct 2026 · ACCT-001
- **What:** two things, in this order:
  1. A filter on `GET /orders` (and `/orders/stats`, `/orders/export`) for **whose approval is
     next**: `waiting_on=account_manager` (any role code), matching the row's
     `approval_waiting_on`. Paged and counted like the other filters.
  2. Is there anything Accounts records **besides** the approval remark, such as a payment
     received, its mode and reference, or an advance against the order? RBAC.md §6 lists a
     `payments` module (Accounts `V:global CEA`), but no endpoint serves it. If payments are
     planned, the contract for them; if not, say so and the queue stays the approval step alone.
- **Why:** the plan gives Accounts its own working screen. Today Accounts' steps arrive in
  the Approvals inbox (APPR-001), which works. But a queue of "orders at the payment check",
  showing what each is waiting for, can't be built: `GET /orders` can't filter on
  `approval_waiting_on`, and filtering on the screen would break paging and the count. The
  sidebar's "Accounts queue" stays "Soon" until then.
- **Done when:** `GET /orders?waiting_on=account_manager` returns only the orders whose next
  step is Accounts, with `include_total`. And there is a decision on payments: either a
  contract, or "none planned".
- **Done in:** #75
- **Backend notes:** `waiting_on=<role code>` on `GET /orders`, `/orders/stats` and `/orders/export`: same rule as the row's `approval_waiting_on`. An unknown code is an empty page; a malformed one is `422`. For the badge, call stats without it and read `waiting_on.account_manager`. Part 2: payments are built (FS-022, handover `payments-contract.md`): `GET/POST /payments`, and `payments` on `GET /orders/{id}`. No new contract.

### BE-023 · Find a lead's subsidy application: a `lead_id` filter on `GET /subsidy-applications`

- **Status:** ✅ Done
- **Asked:** 9 Oct 2026 · SUBS-005
- **What:** `GET /subsidy-applications?lead_id=` — the applications of one lead, newest first,
  in the caller's scope. The same filter on `/subsidy-applications/export` is welcome but not
  needed.
- **Why:** the handover asks for "a tab on the lead: its application, if any", and the lead
  page needs it to decide whether to offer "Start subsidy application" (a lead with a live
  application gets `422 already_forwarded`). Today nothing finds a lead's application:
  `q` matches the application number, the Reg. No. and the farmer's name (not the lead), and the
  lead's timeline events (`subsidy.created` …) don't carry the application's id. The frontend
  already sends `lead_id` and keeps only the rows whose `lead.id` matches, so until the filter
  exists the lead's card may miss an application that isn't on the first page.
- **Done when:** `GET /subsidy-applications?lead_id=<uuid>` returns only that lead's
  applications.
- **Done in:** #190
- **Backend notes:** `GET /subsidy-applications?lead_id=<uuid>`, on `/export` too. That lead only, in your scope; leads merged into it are not followed. Empty means none you can see, not none exists: an application keeps the owner it was forwarded with, so a lead's later owner may get `[]` and Forward still answers 422 `already_forwarded` (GAP-512). Keep handling that.


### BE-024 · List the product categories and units: `GET /lookups/product-categories`, `GET /lookups/uoms`

- **Status:** ✅ Done
- **Asked:** 11 Oct 2026 · MSTR-004
- **What:** two lookups the product form can offer as choices:
  - `GET /lookups/product-categories`: every category code (migration 010's seeds: DRIP
    COMPONENTS, HDPE PIPES, … Marketing) with its label and whether it is active.
  - `GET /lookups/uoms`: every unit code with its `decimals` (NOS. 0, MTR 3, Set. 0, ML 0).
  Same shape as the other lookups (`{ data: [{ code, name, is_active, … }] }`).
- **Why:** `POST /products` refuses a `product_category` or `uom` that isn't a code, but nothing
  lists the codes. Until then the product form offers the categories and units the catalogue
  already uses, read from every page of `GET /products` (active and switched off). That works,
  but a category with no product yet can't be chosen, and it costs a few calls each time the
  form opens.
- **Done when:** both endpoints answer for anyone who may view `products`, and the form offers
  every code, used or not.
- **Done in:** #190
- **Backend notes:** `GET /lookups/product-categories` → `{id, code, name, sort_order, is_active}`; `GET /lookups/uoms` → `{id, code, name, decimals, is_active}`. Both need `products.view` (403 otherwise). Switched-off rows are listed, soft-deleted ones are not. `POST /products` does not refuse an inactive code, so hiding it is the form's job.


### BE-025 · Offer only the document types a record takes: `record_type` on `GET /documents/types`

- **Status:** ✅ Done
- **Asked:** 13 Oct 2026 · DOC-002
- **What:** `GET /documents/types?record_type=lead` (and the other record types) answers only the
  types that belong on that record. Without the filter, the answer stays as today: every type.
- **Why:** the list has 15 types. The last five (GST certificate, PAN card, cancelled cheque, shop
  photo, shop licence, FS-051) are a dealer application's. They show in the type picker on a lead,
  a quotation, an order and a dispatch, where nobody should choose them. The frontend builds the
  picker from this list as the handover says, and won't hard-code which types to hide.
- **Done when:** the filter answers the record's types only. The frontend will send the record's
  type and drop nothing itself.
- **Done in:** #190
- **Backend notes:** `GET /documents/types?record_type=lead|quotation|sales_order|dispatch|payment|dealer_application`. A dealer application answers its five types and `other`; every other record the ten general types. Omitted: every type, as before. Unknown: 422. The upload itself still accepts any type (GAP-516).


### BE-026 · Show a list row's sort order, quality and kind: return them on `LookupItem`

- **Status:** ✅ Done
- **Asked:** 15 Oct 2026 · MSTR-009
- **What:** `GET /lookups/{list}` (and the `POST`/`PATCH` answers) carry each row's `sort_order`
  for sources and reasons, `quality` for sources, and `kind` for reasons, as `LookupCreate` takes
  them. Null where a list has none.
- **Why:** Masters sets them when a row is added, and `PATCH` can change `sort_order` and
  `quality`, but the list answers only `id`, `code`, `name` and `is_active`. So the screen can't
  show a source's quality or a row's place, and changing one would be blind. For now Masters asks
  for them only when adding a row.
- **Done when:** the three fields come back on every list row. The frontend will show them and
  offer to change sort order and quality in place.
- **Done in:** #190
- **Backend notes:** Every row of the lookup lists, and the POST/PATCH answers, carry `sort_order`, `quality`, `kind` (null where the list has none). `quality` is shown only to `masters.edit`, null for everyone else. `kind` on lost-reasons is always `lost`: won reasons are listed nowhere yet (GAP-513). `sort_order` is bounded to ±1,000,000. Answers show stored values: `quality` 0.555 comes back `"0.56"`.


### BE-027 · Name a scheme's targets, and list product categories with their ids

- **Status:** ✅ Done
- **Asked:** 16 Oct 2026 · SCHM-001, SCHM-002
- **What:**
  - Each entry of a scheme's `targets` gains `name`: the territory's, partner's, product's or
    category's name (for `partner_type`, the type itself is enough).
  - `GET /lookups/product-categories` (BE-024) answers each category's `id` beside its code,
    since a `product_category` target takes the id.
- **Why:** a scheme answers its targets as `{ type, id }` only. The frontend reads each name from
  its own record (`GET /territories/{id}`, `/partners/{id}`, `/products/{id}`): one call per target,
  and each needs access to that record. Someone who may view schemes but not masters sees "Territory
  1a2b…" instead of "Rajkot". No endpoint lists category ids, so the scheme form can't offer a
  product category at all.
- **Done when:** targets come with their names, and the categories come with their ids. The
  frontend then drops the per-target calls and offers categories in the form.
- **Done in:** #190
- **Backend notes:** Each target on every scheme read carries `name` (for `partner_type`, the type). Null outside your scope; a partner user never sees `partner` targets. Category ids: `GET /lookups/product-categories` (BE-024). `name` is accepted and ignored on input, so echoing targets is fine, but send `targets` on PATCH only when they changed: on a used scheme any `targets` key answers 409 `scheme_in_use`.


### BE-028 · Say which roles may order, approve and send marketing material: default grants for `marketing_material`

- **Status:** ✅ Done
- **Asked:** 17 Oct 2026 · MKT-002, MKT-003, MKT-004
- **What:**
  - Migration 038 checks `marketing_material` (view, create, approve, edit, delete) but seeds no
    role grants, so on a fresh database nobody but a role edited by hand can open the screens.
  - Seed the defaults the handover describes, or say who gets what: dealers and field staff order
    (view, create); the District Manager over the office approves (approve); the marketing team
    keeps the catalogue and records dispatch (edit); Admin everything.
  - Add the `marketing` role's grants, since it is a functional role in `/roles`.
- **Why:** the frontend gates the menu item and every button on these permissions. The mock grants
  them as above for now; without seeded grants the page is hidden for everyone on staging.
- **Done when:** `GET /auth/me` returns `marketing_material` for those roles on a fresh database.
  The frontend then checks the mock against the seeded grants.
- **Done in:** #190
- **Backend notes:** Nothing to build: RBAC.md already grants `marketing_material` (dealers and field staff view+create; DM, SM approve; RM view+approve; marketing, admin, MD everything; board view), and the seeds carry it. Staging's `GET /auth/me` returns it for those roles. Please check the mock against staging.


### BE-029 · List only the quotations still free to order: an `orderable` filter on `GET /quotations`

- **Status:** ✅ Done
- **Asked:** 18 Oct 2026 · SO-011
- **What:**
  - Place order now offers the dealer's other accepted quotations, to make one consolidated
    order (`POST /orders` with several `quotation_ids`). The list comes from
    `GET /quotations?status=accepted&partner_id=…`.
  - That list can't tell which of them are already on a live order. Add `orderable=true`
    (accepted, current, and not on a live order), or an `order` reference on each row.
- **Why:** today a quotation already on an order shows as a choice. The frontend learns it only
  when `POST /orders` answers `409 quotation_on_order`; it then unticks and marks that quotation.
- **Done when:** the filter (or the field) is in `quotations.md`. The frontend then lists only the
  free ones.
- **Done in:** #190
- **Backend notes:** `GET /quotations?orderable=true`: accepted, current, not deleted, on no live order (a draft, the caller's own included, or an order returned by an approver holds it; cancel or delete releases it). Combine with `partner_id` or `lead_id`. It narrows, it does not promise: an order you cannot see may hold a listed quotation, so keep handling 409 `quotation_on_order`.


### BE-030 · Say on `GET /auth/me` whether tasks are on for dealers (`tasks_for_dealers`)

- **Status:** ✅ Done
- **Asked:** 18 Oct 2026 · TASK-009, AUTH-002
- **What:**
  - A partner user can't read `GET /settings`. To learn whether `tasks_for_dealers` is on, the
    frontend asks for the user's open tasks and reads a `403` as "off".
  - Return the switch with the session instead, for example `features: { tasks_for_dealers: true }`
    on `GET /auth/me`, or leave the `tasks` grant out of a partner user's permissions while it is off.
- **Why:** while the switch is off, every page a dealer, distributor or sub-dealer opens makes one
  refused `GET /tasks` call. The browser logs that as an error, which hides real ones in a walk.
- **Done when:** `GET /auth/me` says whether tasks are on, or the grant follows the switch. The
  frontend then drops the probe.
- **Done in:** #190
- **Backend notes:** `GET /auth/me` → `features: { tasks_for_dealers: bool }`, true when the setting is `on`. `permissions` still lists `tasks` for portal roles, so check both. Read once per session: after the admin flips the switch, a `/tasks` call can still answer 403.


### BE-031 · A complaint's PDF, like a quotation's or an order's: `pdf_state` and `GET /complaints/{id}/pdf`

- **Status:** ⬜ Open
- **Asked:** 21 Oct 2026 · CMPL-013 · the user's decision on F-12 (20 Oct)
- **What:**
  - Once the QC verdict is in, files on a complaint stay locked, as today. The user wants a
    **Download PDF** on the complaint instead, like the quotation and the sales order.
  - Proposed, in the order's shape so the same button works:
    - `pdf_state` on the complaint: `none` for a draft, then `pending`, `ready` or `failed`. Render
      again when the complaint changes (a verdict, a remedy, closing, reopening).
    - `GET /complaints/{id}/pdf` returning `PdfLink` (`url`, `expires_at`, `filename`), a link that
      lasts ten minutes. `404` for a draft, `409 pdf_pending` and `409 pdf_failed` as on orders.
  - What the PDF holds is the backend's call. A suggestion: the number, status and severity; the
    contact, place, partner, lead and order; the lines with quantities; the check, the QC verdict
    and the remedy; and the history.
- **Why:** the complaint page has no printable copy to send or file. Quotations and orders have one.
- **Done when:** both are in `complaints.md`. The frontend already shows the button when
  `pdf_state` arrives, and the mock follows the shape above.
- **Done in:** —
- **Backend notes:** —

### BE-032 · A device token for the tracking app, so points upload while the app is closed

- **Status:** ⬜ Open
- **Asked:** 21 Oct 2026 · TRK-008 · the Android tracking app (`Frontend/Docs/handoff-mobile-app.md`)
- **What:**
  - The app's background part is native code that runs while the app's screens are closed. It
    can't use the web session:
    - the access token lives only in the page's memory and lasts 15 minutes;
    - the refresh cookie rotates. If both the web screens and the native part refreshed, one of
      them would reuse a used token, and `refresh_reused` signs the person out everywhere.
  - Proposed:
    - `POST /tracking/device-token` with `{ device_id }`, signed in as usual. It returns a
      long-lived token that is good **only** for `POST /locations/batch`,
      `POST /tracking/duty/end` and `GET /me/tracking-config`, for that user and that device.
    - It stops working when the person signs out, is deactivated or signed out everywhere, or
      withdraws consent. A new call for the same device replaces the old token.
    - The lifetime is the backend's call. A suggestion: 30 days, renewed whenever the app opens.
- **Why:** without it, points wait on the phone until the person next opens the app. Nothing is
  lost, since points are kept up to the retention period. But the team map shows field staff as
  "stale" all day, and the day's km appear only after the app is opened.
- **Done when:** it is in `tracking.md`, and in the contract's sequence in
  `handover/field-tracking-contract.md`.
- **Done in:** —
- **Backend notes:** —

### BE-033 · Restore a deleted lead, and say when and by whom it was deleted

- **Status:** ⬜ Open
- **Asked:** 22 Oct 2026 · LEAD-019 · the Deleted leads list
- **What:**
  - `GET /leads?deleted=true` lists deleted leads "to restore one", but nothing restores one. Proposed:
    `POST /leads/{id}/restore`, needing `leads.delete`. It clears `deleted_at` and adds a
    `lead.restored` event to the timeline. A lead that isn't deleted answers `200` unchanged.
  - Say on each row of `GET /leads?deleted=true`: `deleted_at`, and `deleted_by` as
    `{ id, full_name }`. The list could then show when and by whom, and sort by it.
  - Say whether `GET /leads/{id}` opens a deleted lead for a `leads.delete` holder. Until then the
    list doesn't link to it: the page would offer edits and stage changes on a lead nobody else
    can see.
  - What a restore does to the duplicate pairs the delete closed is the backend's call.
- **Why:** a lead deleted by mistake can be found but not brought back. Today only a database edit
  undoes it.
- **Done when:** it is in `leads.md`. The frontend adds a **Restore** button to each row, the dates,
  and a link to the lead if it opens.
- **Done in:** —
- **Backend notes:** —

### BE-034 · Redeploy the API on the test box from `integration`: none of BE-023 to BE-030 is live

- **Status:** ⬜ Open
- **Asked:** 23 Oct 2026 · APP-009 · live test issue 1 (`Frontend/Docs/Live-Test-Report.md`)
- **What:**
  - `https://polysil-api.pranayx.tech/openapi.json` (296 paths) lacks every change from #190, though
    BE-023 to BE-030 are ticked Done:
    - `GET /lookups/product-categories` and `GET /lookups/uoms` → 404;
    - `lead_id` on `GET /subsidy-applications`;
    - `orderable` on `GET /quotations`;
    - `record_type` on `GET /documents/types`;
    - `sort_order`, `quality` and `kind` on lookup rows;
    - `tasks_for_dealers` on `GET /auth/me`.
  - Please redeploy that API from the current `integration` (BE-019 says it follows `integration`), and
    say on this item when it is done.
- **Why:**
  - New products can't be added: the Category and Unit pickers are empty.
  - Masters show "—" for order and quality. Saving a lead source there may blank its quality score
    (not tried).
  - A lead is offered dealer document types.
  - "Place order" can't filter to quotations free to order.
- **Done when:** `/openapi.json` has the paths and fields above. The frontend then re-runs cases
  V-02, V-04, V-05 and Y-10 to Y-15 of the live test plan.
- **Done in:** —
- **Backend notes:** —

### BE-035 · Refuse a quotation with no items (`POST /quotations`, and sending an empty draft)

- **Status:** ⬜ Open
- **Asked:** 23 Oct 2026 · QUOT-004, QUOT-006 · live test issue 2 (I-03)
- **What:**
  - `POST /api/v1/quotations` with `"lines": []` answers `201` and makes a ₹0 draft
    (x-request-id `a19a01ac-ff47-458e-a246-4beb63247116`). That draft can then be sent.
  - The frontend now keeps Save off until there is an item (APP-009). The API should refuse it too, as
    any other client could still send it. Proposed: `422 lines_required` (`fields.lines`) on create,
    on `PUT /quotations/{id}/lines` with no lines, and on send for a draft with none.
- **Why:** a ₹0 quotation with no items reached the Send button on the test box.
- **Done when:** it is in `quotations.md`. The frontend shows the error on the items.
- **Done in:** —
- **Backend notes:** —

### BE-036 · The dashboard's overdue follow-ups say 0 while Tasks shows 1 overdue

- **Status:** ⬜ Open
- **Asked:** 23 Oct 2026 · RPT-001, TASK-001 · live test issue 6 (C-01)
- **What:**
  - As `ravi@polysil.in`:
    - `GET /api/v1/dashboard/overview` gives **0** for "Overdue follow-ups" ("Open tasks past their due
      date");
    - Tasks → My day shows **1** overdue: *TEST walk 10oct task for ravi*, a Follow-up due 10 Oct
      6 pm, given by Asha Patel;
    - Asha's Team view counts it too.
  - Either the overview's count misses it (a follow-up given by someone else? one due before this
    month?), or the card counts something narrower. If narrower, say what, and the frontend will
    relabel the card.
- **Why:** the same person sees two different numbers for the same thing.
- **Done when:** the two agree, or `dashboard.md` says what the card counts.
- **Done in:** —
- **Backend notes:** —

### BE-037 · Decide: may a state manager delete leads? The test box grants it; RBAC.md and the mock don't

- **Status:** ⬜ Open
- **Asked:** 23 Oct 2026 · LEAD-011, LEAD-019 · live test issue 10 (Y-09)
- **What:**
  - On the test box, `GET /auth/me` for `gujarat@polysil.in` (state manager) has `leads` `delete`
    (org_subtree), so that user sees **Delete** on a lead and the **Deleted leads** list.
  - The frontend's mock, following RBAC.md, gives `leads.delete` to Admin only.
  - The screens follow whatever `/auth/me` says, so nothing changes in the frontend either way.
- **Why:** a state manager can delete any lead in the state. That may be intended, or a seed left
  over.
- **Done when:** RBAC.md and the seed agree, and the frontend's mock is set to match.
- **Done in:** —
- **Backend notes:** —

### BE-038 · Decide: may a dispatch take a warehouse's stock below zero?

- **Status:** ⬜ Open
- **Asked:** 23 Oct 2026 · DISP-002, MSTR-015 · live test issue 7 (N-04, O-02)
- **What:**
  - Dispatch D/SO/GJ/2026-27/00013/1 (200 MTR) was recorded from "Main warehouse", which had no
    stock (`POST /orders/…/dispatches` → 201, x-request-id
    `90ab8736-453a-46a2-9931-acc818b08e4b`). Its stock went to −500 MTR.
  - An order's shortfall warning never blocks the order, by design. Whether a **dispatch** may go
    out without stock is a business rule for the client.
  - The frontend now words the shortfall as "Warehouse short by 500 MTR" instead of "-500 MTR
    available" (APP-009).
- **Why:** stock below zero means the books and the warehouse disagree.
- **Done when:** the rule is decided. If dispatches must not take stock below zero:
  `409 insufficient_stock` on the dispatch, and the frontend shows it.
- **Done in:** —
- **Backend notes:** —


### BE-039 · A quotation for a dealer or distributor, with no farmer's lead

- **Status:** ⬜ Open · **can start now**
- **Asked:** 24 Oct 2026 · QUOT-004, QUOT-006 · the client: "employees can't process existing dealers' and distributors' quotations"
- **What:**
  - Today `POST /quotations` needs a `lead_id`: every quotation is a farmer's. The client needs quotations where **the dealer is the buyer**, buying stock, with no farmer involved.
  - Proposed: `lead_id` optional on `POST /quotations` when `partner_id` is given, for staff with `quotations.create`.
    - The party defaults from the partner record (name, mobile, address, GSTIN), and the place of supply from its territory. Both can be overridden, as today.
    - Priced at the partner's tier, as today with `partner_id`.
  - Send (`channel: whatsapp`), PDF, approval and "Place order" behave as for a lead's quotation. The order from it has the dealer as the party, as SO-011 does.
  - Lists and filters (`GET /quotations?partner_id=`) need to work without a lead; the lead column is empty.
- **Why it can start now:** the client's open questions 6 and 7 (approvals, delivery address) only change defaults. The defaults above match how orders already work.
- **Done when:** it is in `quotations.md`. The frontend then adds "New quotation for a dealer", reusing the dealer picker built for SO-012.
- **Done in:** —
- **Backend notes:** —

### BE-040 · The employee(s) who look after a dealer or distributor

- **Status:** ⬜ Open · **the link can start now; what it grants waits on the client**
- **Asked:** 24 Oct 2026 · CHNL-001 · the client: "there is no employee selection in dealer, need to add employees in dealer"
- **What:**
  - **Can start now:**
    - Store which staff users look after each partner, allowing **several per partner**. That covers either answer to question 1.
    - Read it on `GET /partners/{id}` and the list, and set it on `POST` and `PATCH /partners`.
    - Filter `GET /partners?employee_id=` and `GET /lookups/partners?mine=true`, for "my dealers".
  - **Waits on the client** (questions 2–5): whether a sub-dealer follows its dealer's employee; who may set it (Admin only, or managers too); what it grants (the dealer's orders, payments, ledger and credit); and whether only the assigned employee may make the dealer's quotations and orders.
- **Done when:** the link is in `partners.md`. The frontend adds the field to the partner form and "My dealers". The rules follow the client's answers.
- **Done in:** —
- **Backend notes:** —

### BE-041 · An employee's leads go to their dealer when the employee leaves

- **Status:** ⬜ Open · **waits on the client**
- **Asked:** 24 Oct 2026 · ADMN-004, LEAD-008 · agreed with the client earlier; questions 8–11 of the client document
- **What:**
  - Today `POST /users/{id}/handover` moves a leaver's open leads to another **employee**.
  - The client wants them to go to **the leaver's dealer** (BE-040), who then handles them.
  - Open:
    - which dealer, when the employee had several (the lead's own partner, one the admin picks, or one in the lead's area);
    - leads with no dealer to go to: the manager?
    - does the dealer become the owner, or do the leads wait for a new employee;
    - automatic on deactivation, or the admin's choice each time.
- **Done when:** the client answers, and the rule is in `users.md`.
- **Done in:** —
- **Backend notes:** —
