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

## Checklist

**Leads**

- [ ] **BE-001** · Sorting on `GET /leads` · LEAD-001 · normal
- [ ] **BE-002** · A next follow-up date on a lead · LEAD-001, LEAD-003, RPT-001 · high
- [ ] **BE-003** · Crops and land (acres) on a lead · LEAD-003 · normal
- [ ] **BE-004** · Win probability and weekly activity — or confirm they are replaced · LEAD-001, LEAD-003 · low
- [ ] **BE-005** · Which territory levels a lead may sit in · LEAD-002 · normal
- [ ] **BE-006** · Names in the `lead.assigned` timeline payload · LEAD-005 · low
- [ ] **BE-007** · Lead counts by source and by inquiry type on `GET /leads/stats` · LEAD-004, RPT-001 · normal

**Modules the frontend still mocks**

- [ ] **BE-008** · Dashboard figures · RPT-001 · high
- [ ] **BE-009** · In-app notifications · NOTIF-001, NOTIF-002 · high
- [ ] **BE-010** · Staff messages · MSG-001…MSG-005 · normal

**Repository and environments**

- [ ] **BE-011** · Merge the tasks (FS-014) and complaints (FS-015) contracts into `integration` · TASK-001, CMPL-001 · normal
- [ ] **BE-012** · Keep the dev API on the latest `integration`, and share the test password · OBS-002 · high
- [ ] **BE-013** · Fix the pagination row in the API docs' conventions · OBS-002 · low
- [ ] **BE-014** · Approval threshold amounts per role · APPR-001 · normal

**Quotations** — added as the quotation screens are built (QUOT-001…).

- [ ] **BE-015** · Point quotation share links at the app: set `PUBLIC_WEB_URL` · QUOT-002 · high
- [ ] **BE-016** · Say whether the dev API renders real PDFs · QUOT-003 · normal
- [ ] **BE-017** · Name the quotation on its events in the lead's timeline · QUOT-010 · normal

---

## Details

### BE-001 · Sorting on `GET /leads`

- **Status:** ⬜ Open
- **Asked:** 22 Sep 2026 · LEAD-001 · Frontend-Scope §10 question 14
- **What:** accept `sort` = `created_at` | `farmer_name` | `estimated_value` and `order` = `asc` |
  `desc` on `GET /leads`, keeping keyset paging (the cursor carries the sort key).
- **Why:** the lead table's sort arrows already send these; today the list is always newest first,
  so clicking Customer or Value does nothing.
- **Done when:** the list comes back in the asked order, page after page, with no gaps or repeats.
- **Done in:** —
- **Backend notes:** —

### BE-002 · A next follow-up date on a lead

- **Status:** ⬜ Open
- **Asked:** 22 Sep 2026 · LEAD-001, LEAD-003, RPT-001 · Frontend-Scope §10 question 15
- **What:** a `next_follow_up_at` (ISO date-time, nullable) on `Lead`, settable when a note is added
  or by a small `PATCH`, and a filter `follow_up_due=today|overdue` on `GET /leads`.
- **Why:** the Follow-up column and field show "—"; the dashboard's "overdue follow-ups" figure and
  list cannot be real without it.
- **Done when:** a lead carries the date, it can be set and cleared, and the list can filter on it.
- **Done in:** —
- **Backend notes:** —

### BE-003 · Crops and land (acres) on a lead

- **Status:** ⬜ Open
- **Asked:** 22 Sep 2026 · LEAD-003 · Frontend-Scope §10 question 16
- **What:** `crops` (codes from an admin list, several) and `land_acres` (decimal string, nullable)
  on `Lead`, in create and `PATCH`.
- **Why:** captured on field visits; the lead page shows "—" for both.
- **Done when:** both are on `Lead`, in `LeadCreate` and `LeadPatch`, with a `GET /lookups/crops`
  list (or say which existing list to use — `GET /subsidy/crops`?).
- **Done in:** —
- **Backend notes:** —

### BE-004 · Win probability and weekly activity — or confirm they are replaced

- **Status:** ⬜ Open
- **Asked:** 22 Sep 2026 · LEAD-001, LEAD-003 · Frontend-Scope §10 question 17
- **What:** either a `win_probability` (0–100) and a weekly interaction count on `Lead`, or a
  decision that `score` replaces win probability and the timeline replaces weekly activity.
- **Why:** the lead page has two cards and the table two columns that show "—". A decision is
  enough — the frontend removes them.
- **Done when:** decided (💬 is fine), with the fields if they stay.
- **Done in:** —
- **Backend notes:** —

### BE-005 · Which territory levels a lead may sit in

- **Status:** ⬜ Open
- **Asked:** 22 Sep 2026 · LEAD-002 · Frontend-Scope §10 question 18
- **What:** the docs say a lead sits in a taluka or district, but `GET /lookups/territories` also
  returns villages and the state. Either refuse the other levels on `POST /leads`, or filter them
  out of the search (a `levels=district,taluka` parameter would do).
- **Why:** the New lead form's territory picker offers what the search returns.
- **Done when:** the rule is decided and enforced in one place.
- **Done in:** —
- **Backend notes:** —

### BE-006 · Names in the `lead.assigned` timeline payload

- **Status:** ⬜ Open
- **Asked:** 27 Sep 2026 · LEAD-005, LEAD-008
- **What:** add `owner_name` and `partner_name` next to `owner_user_id` and `assigned_partner_id`
  in the `lead.assigned` event's payload, as `actor_name` already is.
- **Why:** the lead's history can only say "changed the owner", not "assigned to Ravi Joshi": the
  payload carries ids, and most people cannot look users up.
- **Done when:** new `lead.assigned` events carry both names (null when cleared). Old events can
  stay as they are.
- **Done in:** —
- **Backend notes:** —

### BE-007 · Lead counts by source and by inquiry type on `GET /leads/stats`

- **Status:** ⬜ Open
- **Asked:** 27 Sep 2026 · LEAD-004, RPT-001
- **What:** `by_source` (source code → count) and `by_inquiry_type` (type → count) in `LeadStats`,
  over the same scope and filters as today.
- **Why:** the old guessed `/leads/summary` had them and the dashboard's "Leads by source" chart
  needs them. With these, the dashboard can use `/leads/stats` instead of a mock for that chart.
- **Done when:** both maps are present, every known code included with 0 when empty.
- **Done in:** —
- **Backend notes:** —

### BE-008 · Dashboard figures

- **Status:** ⬜ Open
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
- **Done in:** —
- **Backend notes:** —

### BE-009 · In-app notifications

- **Status:** ⬜ Open
- **Asked:** 27 Sep 2026 · NOTIF-001, NOTIF-002
- **What:** `GET /notifications` (newest first, with the unread count) and `POST /notifications/read`
  (some ids, or all). The mocked shape is in
  `Frontend/src/features/notifications/api/notifications.schemas.ts`.
- **Why:** the bell in the top bar runs on the mock.
- **Done when:** both endpoints exist in the caller's scope; say which events create notifications.
- **Done in:** —
- **Backend notes:** —

### BE-010 · Staff messages

- **Status:** ⬜ Open
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
- **Done in:** —
- **Backend notes:** —

### BE-011 · Merge the tasks and complaints contracts into `integration`

- **Status:** ⬜ Open
- **Asked:** 27 Sep 2026 · TASK-001, CMPL-001
- **What:** `backend-foundation` has two commits `integration` does not: "Tasks and planner
  contract (FS-014)" and "Complaints contract for the frontend track (FS-015)".
- **Why:** the frontend builds from `integration`; those contracts are not visible there yet.
- **Done when:** merged into `integration`.
- **Done in:** —
- **Backend notes:** —

### BE-012 · Keep the dev API on the latest `integration`, and share the test password

- **Status:** ⬜ Open
- **Asked:** 27 Sep 2026 · OBS-002
- **What:** deploy `https://polysil-api.pranayx.tech` from the latest `integration` after each
  backend merge, and share the test accounts' password with the frontend developer (not in the
  repository — `backend/docs/handover/dev-api-access.md` says to ask).
- **Why:** lead history, notes, stage changes and assignment (LEAD-005…008) are built on the
  contract and tested against the mock, but not yet checked by hand on the dev API.
- **Done when:** the dev API runs the latest `integration`, and the frontend has the password.
- **Done in:** —
- **Backend notes:** —

### BE-013 · Fix the pagination row in the API docs' conventions

- **Status:** ⬜ Open
- **Asked:** 27 Sep 2026 · OBS-002
- **What:** `backend/docs/api/README.md` says "Pagination: `page`, `limit`, `sort`, `q`", but the
  lists page by cursor (`limit`, `cursor`, `meta.next_cursor`, `include_total`).
- **Why:** the README is the first thing anyone reads; it sent the frontend down page numbers once.
- **Done when:** the generator writes the cursor convention.
- **Done in:** —
- **Backend notes:** —

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

- **Status:** ⬜ Open
- **Asked:** 27 Sep 2026 · QUOT-002, QUOT-003
- **What:** set `PUBLIC_WEB_URL` on the dev API (and later staging) to the frontend's origin for that
  environment. It defaults to `http://localhost:3000`, and `share_url` on every sent quotation is built
  from it.
- **Why:** the quotation page shows the customer link with a Copy button, and the WhatsApp message
  carries it. With the default, every link sent from the dev API points at localhost. The public page
  `/q/{token}` is being built on the frontend (QUOT, a later slice).
- **Done when:** a quotation sent on the dev API has a `share_url` on the frontend's dev origin. Write
  the origin in the notes.
- **Done in:** —
- **Backend notes:** —

### BE-016 · Say whether the dev API renders real PDFs

- **Status:** ⬜ Open
- **Asked:** 27 Sep 2026 · QUOT-003
- **What:** `pdf_renderer` can be `html` on a box without WeasyPrint, storing the rendered HTML as the
  document. Say which the dev API uses, and switch it to `weasyprint` if it can.
- **Why:** **Open PDF** opens the signed link in a new tab; if the dev API serves HTML, what the
  frontend developer checks there is not what the farmer receives.
- **Done when:** decided and noted (💬 is fine).
- **Done in:** —
- **Backend notes:** —

### BE-017 · Name the quotation on its events in the lead's timeline

- **Status:** ⬜ Open
- **Asked:** 28 Sep 2026 · QUOT-010, LEAD-005
- **What:** on every `quotation.*` event that `GET /leads/{id}/timeline` returns, add `quotation_id`,
  `quote_no` (null on a draft) and `version` to the payload. The contract lists `from`, `to`, `remark`
  and `actor_name` only.
- **Why:** a lead's history shows "Quotation sent", "Quotation accepted" and so on, but cannot say
  which quotation or link to it when a lead has more than one (a revision, or a second unit).
- **Done when:** the payloads carry the three fields; say in the notes if a dealer should not see
  any of them.
- **Done in:** —
- **Backend notes:** —
