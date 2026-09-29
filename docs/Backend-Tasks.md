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
- [ ] **BE-014** · Approval threshold amounts per role · APPR-001 · normal

**Quotations** — added as the quotation screens are built (QUOT-001…).

- [x] **BE-015** · Point quotation share links at the app: set `PUBLIC_WEB_URL` · QUOT-002 · high
- [x] **BE-016** · Say whether the dev API renders real PDFs · QUOT-003 · normal
- [x] **BE-017** · Name the quotation on its events in the lead's timeline · QUOT-010 · normal

**Approvals** — added as the approval screens are built (APPR-001…).

- [x] **BE-018** · Name the Accounts role code in the approval queue · APPR-001 · normal

**Sales orders** — added as the order screens are built (SO-001…, DISP-002).

- [ ] **BE-019** · Find the order that carries a quotation: a `quotation_id` filter on `GET /orders` · SO-003 · low

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

- **Status:** ⬜ Open
- **Asked:** 21 Sep 2026 · APPR-001 · Frontend-Scope §10 question 7
- **What:** the real discount and order-value limits per role — the seed has stand-in thresholds.
- **Why:** quotation discount approval and order approval depend on them; the screens show the
  backend's answer, but the demo should use the client's numbers.
- **Done when:** the client's figures are in the seed or configured, or the notes say who owes them.
- **Done in:** —
- **Backend notes:** —

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

- **Status:** ⬜ Open
- **Asked:** 29 Sep 2026 · SO-003
- **What:** accept `quotation_id` on `GET /orders` (orders whose `quotations` include it), or add
  `quotation_ids` to `OrderSummary`.
- **Why:** an accepted quotation's page offers "Place order", or "Open order" when a live order
  already carries it — `POST /orders` answers `409 quotation_on_order` otherwise. The list rows
  carry no quotation ids, so today the page lists the lead's orders and reads each live one
  (up to ten) to find the match. One filtered call would do.
- **Done when:** `GET /orders?quotation_id=…` returns the order(s) carrying that quotation, in the
  caller's scope.
- **Done in:** —
- **Backend notes:** —
