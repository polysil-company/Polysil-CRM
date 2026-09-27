# Plan — Polysil Irrigation CRM, Dealer Portal & Field Sales App

> **Status:** DRAFT v0.2 — revised for a 6.5-week window and a test-gated (not review-gated) delivery model.
> **Owner:** Nakul Srivastava (architect)
> **Window:** 6.5 weeks ≈ 32 working days, plus a parallel Week 0 dependency track.

**Changed in v0.3 (2026-08-14):** ERP confirmed as *planned, not live* -> [ADR-019](Docs/Decisions.md) seams, schedule risk drops from +1-1.5 weeks to ~1 day - WhatsApp moves to the client's BSP behind a provider port ([ADR-020](Docs/Decisions.md)), removing Meta verification from the critical path - scale confirmed at 700-800 users / 100+ concurrent -> [ADR-021](Docs/Decisions.md) and a new load-test gate.

**Where the build stands now:** see [§9 Integration status](#9-integration-status--frontend--backend) — updated with every integration pull request.

**Changed in v0.2:** window extended 5 → 6.5 weeks · code review replaced by test gating ([ADR-016](Docs/Decisions.md)) · Field Sales confirmed as a **native app**, moving from Phase 2 into scope · application count fixed at 3 · Meta Lead Ads and rewards pulled back into scope.

---

## 1. Can it be done in 6.5 weeks?

**Yes — for all 62 P1 requirements plus most of what was previously the cut-line — conditional on four things.** That is a real yes, not a hedged one, and here is the arithmetic behind it.

**What changed in our favour:**

| Change | Effect |
|---|---|
| 5 → 6.5 weeks | +30% calendar |
| Line-by-line review dropped | Removes the single largest bottleneck. Review capacity was capping throughput at ~60k reviewed lines; test-gating removes that ceiling |
| Review narrowed to the contract layer | ~2–3k lines still reviewed, not 130k — and it's the 2–3k where tests structurally cannot reach |
| Testing moved onto the models | GPT runs suites on every change; the human cost of verification collapses |

Combined, throughput rises well beyond +30%. **6.5 weeks is the first version of this plan I'd defend without caveats about quality.**

**What it costs.** The saving is not free — it is *transferred*, into work that must actually happen:

- **Acceptance criteria before implementation, for all 73 requirements.** This is now the highest-value artefact in the project. Under a test-gated model, an unwritten acceptance criterion is an untested behaviour. That is roughly 3 days of upfront work in Week 0/1.
- **Adversarial test authorship** — a different model tests than builds ([ISS-012](Docs/Issues.md)). Roughly +25% agent time per feature. Worth every minute: without it, a misunderstood requirement produces a wrong implementation *and* a test confirming it, and nothing catches it.
- **Mutation testing** on business logic, to prove the tests actually detect breakage rather than merely executing code.
- **Generated RBAC test matrix** — ~1,400 role × table × operation assertions including the negative cases, which no human writes by hand.

### The four conditions

The 6.5-week date holds if and only if:

1. **The seven kickoff questions are answered before Day 1** — see [Open-Questions.md §Z](Docs/Open-Questions.md). Especially #4 (permissions for the five undefined roles), which has no safe working assumption and blocks Week 1 outright.
2. ~~Q9 resolves to "CRM is the source of truth."~~ **RESOLVED 2026-08-14 — and in our favour.** The ERP is *planned*, not live, so there is nothing to sync with in Phase 1. We build seams rather than a connector ([ADR-019](Docs/Decisions.md)): about **1 day**, not 1–1.5 weeks. The residual condition is narrower — the **system-of-record ownership table must be signed off before the Week 1 schema freeze** ([Q39](Docs/Open-Questions.md)). If that slips past Day 2, schema freeze slips with it.
3. **Week 0 external dependencies start immediately** — now shorter, because the client's existing WhatsApp BSP removes Meta Business verification (3–15 days) from the critical path. What replaces it is smaller but still blocking: BSP API access and confirmation that **inbound webhooks** exist on their plan ([Q36](Docs/Open-Questions.md)). Without inbound, REQ-601 cannot be built as specified. Still on the calendar-time list: DLT template registration for SMS, and app distribution setup.
4. **Field app is Android-first with internal distribution.** Android + iOS + public store review is a different project on the mobile track — see [ISS-011](Docs/Issues.md).

### Condition 5 — new: scale is designed in, not tuned in later

Confirmed load is **700–800 named users, 100+ concurrent**, against a seasonal business. That is not a large system, but two failure modes at this scale are invisible to every functional test we have: connection exhaustion under serverless fan-out, and RLS policies whose per-row cost is negligible at 50 rows and fatal at 500k ([ISS-018](Docs/Issues.md)).

Neither can be retrofitted cheaply — transaction-mode pooling compatibility and RLS shape are properties of the frozen contract layer. So both land in **Week 1**, where they cost about a day, rather than Week 6 where they cost a rewrite ([ADR-021](Docs/Decisions.md)).

Added to the plan as a consequence:

| Where | What | Cost |
|---|---|---|
| W1 D2 | Supavisor transaction mode; no session state anywhere | in-line |
| W1 D2 | RLS written to the performance discipline; every policy column indexed | in-line |
| W1 D2 | Sync seams — `external_id` / `source_system` / `sync_outbox` / idempotency keys | ~1 day |
| W1 D5 | `scale` seed profile promoted from Week 6 to Week 1 | ~0.5 day |
| Nightly from W2 | k6 load test at **300 concurrent**; RLS `EXPLAIN ANALYZE` assertions | setup ~0.5 day |
| W6 D28 | Dedicated load & soak day at seasonal peak volume | 1 day |

Net effect on the 6.5-week window: roughly **+2 days of new work, offset by ~5 days removed** (no ERP connector, no Meta verification wait). The date holds, with slightly more slack than v0.2 had.

**If any condition fails**, the honest response is to move the cut-line, not the quality bar. Designated cut-line for 6.5 weeks: Sales Forecast Report (REQ-1204), Campaign Performance Report (REQ-1209), Material Planning (REQ-1102), Improvement Insight (REQ-903). Everything else is committed.

---

## 2. What we are building — three applications, one domain model

| # | Application | Type | Users |
|---|---|---|---|
| **1** | **Internal CRM** | Web | Management · Regional/Area Manager · Sales Manager · Sales Executive · Marketing · Accounts · Quality · Support · Admin |
| **2** | **Dealer / Customer Portal** | Web | Distributor · Dealer · Sub-dealer · Agent · Customer/Farmer |
| **3** | **Field Sales App** | Native mobile (Expo) | Sales Executive · Sales Manager — *one app, role-based screens* |

**Apps 1 and 2 are route groups in one Next.js codebase** ([ADR-001](Docs/Decisions.md)) — identical domain model, one deploy, one contract surface. They are separate *applications* to users and separate *route groups* to us; that is the right seam.

**App 3 is one Expo app, not two** ([ADR-017](Docs/Decisions.md)). A Sales Manager gets additional screens and wider data scope through the same role system that already governs the web — not a second binary. One codebase, one build pipeline, one distribution channel, and managers are field-active anyway. The manager-only analytics screens are lazy-loaded so an executive never pays for them.

**Note on Customer/Farmer in App 2:** a farmer and a distributor share almost nothing in navigation, vocabulary or data. Shared codebase is right; shared *interface* is not. Scoped as a distinct lightweight OTP experience inside the same app — pending [Q31](Docs/Open-Questions.md) ([ISS-006](Docs/Issues.md)).

---

## 3. Method — contract-first, test-gated

Two mechanisms carry this project. Neither works without the other.

**Contract-first** — freeze the interfaces before parallel work starts, so four models cannot produce four architectures:

```
1. Requirements register    → Requirements.md, REQ-IDs           [Week 0]
2. Acceptance criteria      → Acceptance-Criteria.md             [Week 0-1]  ← now load-bearing
3. Domain glossary + ERD    → Architecture.md, Glossary.md       [W1 D1]
4. RBAC matrix              → RBAC.md                            [W1 D1]
5. Database schema + RLS    → supabase/migrations/*.sql          [W1 D2]
6. Zod contracts + types    → src/contracts/**                   [W1 D2-3]
7. Service signatures       → src/server/services/**             [W1 D3]
8. API contract (/api/v1)   → for the mobile app                 [W1 D3]
9. Design system            → src/components/ui/**               [W1 D4]
10. Feature implementation  → everything else                    [W2-W6]
```

Layers 3–9 are **⛔ FROZEN** ([AGENTS.md §3](Docs/AGENTS.md)). A model that finds a frozen contract inadequate stops and reports — it does not work around it. Working around it is how a second architecture is born.

**Test-gated** — a requirement ships when its acceptance suite passes, not when someone has read the diff. Full strategy in [Testing.md](Docs/Testing.md). The three rules that make it trustworthy:

1. Acceptance criteria are written **from the requirement, before implementation** — never from the code.
2. **A different model writes the tests** than writes the feature.
3. **Mutation testing** proves the tests detect breakage rather than merely executing lines.

**One hand-built reference vertical slice (Leads)** in Week 1 becomes the template every other module is cloned from. Ten near-identical modules from one proven template is what makes this timeline arithmetic work at all.

---

## 4. Week 0 — starts now, runs in parallel

Not our engineering week. The client-dependency week, and the difference between shipping and slipping.

| # | Action | Owner | Lead time |
|---|---|---|---|
| 0.1 | Answers to the seven kickoff questions ([§Z](Docs/Open-Questions.md)) | Client | 3 days |
| 0.2 | **Full RBAC matrix for all 9 CRM + 5 portal roles** signed off | Client | 3 days |
| 0.3 | Meta Business Manager verification (GST cert + utility bill) | Client | 3–15 working days |
| 0.4 | Dedicated WhatsApp number — must NOT be on consumer WhatsApp | Client | 1 day |
| 0.5 | 12 WhatsApp templates drafted and submitted for approval | Loopify → Meta | 1–3 days each |
| 0.6 | TRAI DLT registration + SMS sender ID + template registration | Client | 5–15 working days |
| 0.7 | **App distribution decision + Play Console / MDM access** | Client | 2–15 working days |
| 0.8 | Product master — SKU, HSN, GST slab, UoM, MRP | Client | 2 days |
| 0.9 | Price lists per channel tier | Client | 2 days |
| 0.10 | Dealer + distributor master with hierarchy mapping | Client | 3 days |
| 0.11 | Brand kit — logo, colours, typography, tone | Client | 2 days |
| 0.12 | Domain, DNS access, email sending domain | Client | 1 day |
| 0.13 | Named client SPOC with decision authority + daily 20-min slot | Client | immediate |
| 0.14 | **Acceptance criteria authored for all 73 requirements** | Opus 5 + Nakul | 3 days |
| 0.15 | Repo ✅, Supabase (ap-south-1), Vercel, Sentry, CI, Expo project | Loopify | 1 day |

> **Gate:** if 0.1, 0.2, 0.8, 0.9 and 0.13 aren't complete by end of Week 1, the date is no longer defensible — and we say so in writing that day, not in Week 5.

---

## 5. The 6.5 weeks

Two tracks run in parallel from Week 3: **web** and **mobile**. Each week ends with a demoable exit criterion. Friday is client demo + UAT feedback, every week, no exceptions — weekly demos are what stop a long build from discovering a misunderstanding at the end.

### Week 1 — Contracts & the reference slice
*No features this week. This is the foundation everything else is generated from.*

| Day | Work | Model |
|---|---|---|
| D1 | Glossary, full ERD, **RBAC matrix → `Docs/RBAC.md`**, module inventory | Opus 5 + Nakul |
| D2 | Postgres schema + migrations, RLS policies, audit trigger, soft-delete convention, closure table | Opus 5 |
| D3 | `src/contracts/**` Zod schemas, generated DB types, service signatures, `/api/v1` contract for mobile, auth (email + OTP) | Opus 5 |
| D4 | Design system, shadcn setup, app shell, role-aware nav, data-table primitive, form primitives, all UI states, i18n scaffolding | Nakul + Sonnet 5 |
| D5 | CI with all gates, Vercel + Supabase envs, Sentry, **generated RBAC test matrix**, both seed profiles, **reference vertical slice: Leads** | Opus 5 + GPT 5.6 Sol |

**Exit:** schema frozen · CI green with the full RBAC matrix passing · Leads working on staging with RBAC + audit + timeline + its complete test suite · every other module now has a template.

### Week 2 — Sales Core
*The internal sales team can run their actual day on the system.*

REQ-101/103/105/106/107/108/109 (leads complete, web-form intake, scoring, dedupe + merge, won/lost) · REQ-301/302/304 (tasks, planner, MOMs) · REQ-006/305 (approval engine) · REQ-007 (notification engine; WhatsApp behind a mock) · REQ-202 (3-way pipeline) · REQ-1301/1302/1303 (RBAC + audit enforced across everything built so far)

**Exit:** a Sales Executive works a full day — leads arrive from a live website form, run through a planner, get a logged visit and MOM, and close won/lost — with a manager seeing only their own team's data, proven by the generated permission suite.

### Week 3 — Quote-to-Order & Channel · *mobile track opens*
*Money starts moving.*

**Web:** REQ-004/005 (product, SKU, HSN, tiered price lists) · REQ-203/204/205/206 (GST engine, instant quote, PDF, lifecycle) · REQ-201 (geo-scoped schemes auto-applied) · REQ-1101/1103/1104/1105/1109/1111 (dealer portal: OTP login, sales order, approval, dispatch status, agent management, promo visibility) · REQ-001 (channel hierarchy end-to-end)

**Mobile:** Expo project, auth against `/api/v1`, app shell, role-based navigation, offline-capable local store, internal distribution pipeline proven end-to-end on a real device

**Exit:** a real dealer logs in on a phone, sees tier pricing with the active Gujarat scheme applied, places an order · a sales exec issues a GST-correct PDF quote · a signed build installs on a real Android device.

### Week 4 — Service, Money & Communication · *mobile: field flows*
*The loop closes.*

**Web:** REQ-801..806 (complaints, SLA timers, QA routing, refund approval, warranty, replacement, ratings) · REQ-1106 (dealer ledger, NEFT/UPI/cheque) · REQ-501/502/503 (subsidy + farmer payment ledger) · REQ-601..605 (WhatsApp Cloud API live — 12 templates, send pipeline, inbound webhook, unified dashboard, consent records) · REQ-403

**Mobile:** REQ-701 (check-in/check-out with GPS + photo) · REQ-702 (background location + route history) · visit logging, task list, lead capture in the field, offline queue with sync

**Exit:** a farmer complaint routes dealer → QA → refund approval with a visible SLA, and WhatsApp confirms each step · a field exec logs a visit offline and it syncs on reconnect.

### Week 5 — Insight & the rest of scope · *mobile: manager*
REQ-901/902 (360° timeline, drop-off identification) · REQ-1001 (role dashboards) · REQ-1201..1211 (reports + exports) · REQ-401/402/1107 (rewards & gifting) · REQ-102/104 (Meta Lead Ads + Google Ads intake, if App Review has cleared) · REQ-1112 (consumer portal) · REQ-1002 (Hindi + Gujarati content loaded)

**Mobile:** REQ-703 (manager screens — team map, visit compliance, performance)

**Exit:** every committed requirement is functionally complete on staging.

### Week 6 — Hardening
*No new features after Wednesday. This is where quality is either present or absent.*

| Day | Work |
|---|---|
| D26–27 | Full scenario suites from [Testing.md §5](Docs/Testing.md) — data shapes, lifecycle, permissions, integration failures, environment, money |
| D28 | Performance at scale seed (500k+ rows), report query budgets, low-end Android profiling, 3G dealer-portal budget |
| D29 | Mutation testing pass, gap closure, RLS penetration testing, a11y (WCAG 2.2 AA) sweep, Gujarati typography at 360px |
| D30 | Security review, Sentry triage, error-state audit, manual checklist, **data migration dry run** |

### Week 6.5 — UAT & cutover
| Day | Work |
|---|---|
| D31 | Client UAT with real users — a real sales exec, a real dealer |
| D32 | UAT burn-down |
| D33 | Production data migration, cutover, training session, handover docs, 30-day support plan |

**Exit:** production live on the client's domain, real data migrated, field app distributed, UAT signed off, team trained.

---

## 6. Cadence & quality gates

**Daily**
- 09:30 — Nakul sets the day's contract: REQ-IDs, assigned model, paired test-author model. Written before any agent runs.
- One REQ-ID per branch, one PR per REQ-ID.
- CI runs on every push. **Merge is blocked on green, not on approval.**
- 17:00 — merge window. Nakul merges anything green whose Definition of Done is complete, and reviews only contract-layer changes.

**Nightly on `main`:** full Playwright suite · mutation testing · performance at scale · visual regression. **A red nightly stops new feature merges until green** — the rule that keeps a suite from rotting into decoration.

**Definition of Done** — 13 items, in [AGENTS.md §6](Docs/AGENTS.md). The first three matter most now: every acceptance criterion has a passing test · the tests were written by the paired model from the criteria, not from the code · scenario coverage applied.

**Weekly:** Friday 15:00 client demo on staging with realistic Gujarat data. Feedback becomes REQ rows, never verbal scope. Friday 17:00 retro into [Learning.md](Docs/Learning.md); risk register re-scored.

---

## 7. Risk register

| # | Risk | Impact | Mitigation | Owner |
|---|---|---|---|---|
| R1 | **Q9 resolves to two-way ERP sync** | +1–1.5 weeks; order/stock/ledger rebuild | Force the answer in Week 0. Largest remaining schedule risk | Client |
| R2 | **Play Store background-location review** exceeds the window | Field app undeliverable | Internal distribution — signed APK / Managed Play. Bypasses store review entirely ([ISS-011](Docs/Issues.md)) | Client + Nakul |
| R3 | **AI tests validate AI misunderstandings** | Green suite, broken product | Adversarial pairing + criteria-first + mutation testing ([ISS-012](Docs/Issues.md)) | Nakul |
| R4 | Meta/WhatsApp verification slips past Week 4 | REQ-601..604 unshippable | Started Day 1; built behind a mock provider so it's demoable regardless; SMS + email fallback | Client |
| R5 | The 5 undefined CRM roles stay undefined | Week 1 foundation blocked | No safe assumption exists. Escalate immediately if not answered by Day 3 | Client |
| R6 | Business rules answered late | Rework, guessed logic | Nothing `SPEC` enters a sprint; the register makes it visible daily | Client SPOC |
| R7 | Scope creep at weekly demos | Silent timeline loss | Every demo request becomes a REQ row with a tier before it becomes code | Nakul |
| R8 | **Schema mistake invisible to functional tests** | Rebuild in month 3 | Contract layer is the one thing still human-reviewed — ~2–3k lines ([ISS-013](Docs/Issues.md)) | Opus 5 + Nakul |
| R9 | Performance collapses at real data volume | Reports time out post-launch | `scale` seed profile in CI from Week 1; explicit query budgets ([ISS-014](Docs/Issues.md)) | GPT 5.6 Sol |
| R10 | Hindi/Gujarati content not supplied | Ships English-only | Keys wired Week 1; content is a named client deliverable, due Week 4 | Client |
| R11 | Four models drift into four architectures | Unmaintainable codebase | Frozen layers + reference slice + [AGENTS.md](Docs/AGENTS.md) | Nakul |
| R12 | DPDP exposure — farmer PII, employee tracking | Regulatory | ap-south-1, consent records, retention policy, PII scrubbing, employment policy basis | Nakul + client legal |
| R13 | Mobile track starves the web track | Both slip | Mobile is a dedicated model from Week 3 against a frozen `/api/v1`; the tracks don't share files | Nakul |

---

## 8. Practices adopted

| # | Practice | Status |
|---|---|---|
| 1 | Requirements register with REQ-IDs | ✅ [Requirements.md](Docs/Requirements.md) |
| 2 | Open questions with named owners | ✅ [Open-Questions.md](Docs/Open-Questions.md) |
| 3 | Issues log | ✅ [Issues.md](Docs/Issues.md) |
| 4 | Testing strategy | ✅ [Testing.md](Docs/Testing.md) |
| 5 | Acceptance criteria per requirement | 🔨 [Acceptance-Criteria.md](Docs/Acceptance-Criteria.md) — format set, authoring in Week 0 |
| 6 | ADR discipline | ✅ [Decisions.md](Docs/Decisions.md) |
| 7 | Private git repo, protected `main` | ✅ |
| 8 | `Docs/RBAC.md` — full role × module matrix | ⬜ Week 1 D1, blocked on Q32 |
| 9 | `Docs/Glossary.md` — domain terms | ⬜ Week 1 D1 |
| 10 | `Docs/Integrations.md` | ⬜ Week 1 |
| 11 | `Docs/Security.md` — RLS model, PII inventory, DPDP | ⬜ Week 2 |
| 12 | `Docs/Runbook.md` — envs, deploy, rollback, on-call | ⬜ Week 6 |
| 13 | `Docs/UAT.md` — client-signed acceptance per REQ-ID | ⬜ Week 5 |
| 14 | CI as a hard merge gate | ⬜ Week 1 D5 |
| 15 | Feature flags | ⬜ Week 1 |
| 16 | Two seed profiles (`demo`, `scale`) | ⬜ Week 1 D5 |
| 17 | Per-PR preview deploys | ⬜ Week 1 D5 |
| 18 | Mutation testing on business logic | ⬜ Week 2 |
| 19 | Generated RBAC test matrix | ⬜ Week 1 D5 |

---

## 9. Integration status — frontend ↔ backend

> **Living section.** Update it in the same pull request that connects or disconnects a screen. Last updated **27 September 2026**: PR #8 and PR #18 merged; lead actions (LEAD-005…008) built on `claude/integration-branch-review-gw0r1g`.

**How the two sides meet.** The browser calls `/api/v1` on the app's own origin; `next.config.ts` forwards it to `API_PROXY_TARGET`. Every call goes through `apiRequest` (`src/lib/api/client.ts`): Zod-validated responses, `x-request-id` / `x-data-id`, `Idempotency-Key` on mutations, one refresh-and-retry on a 401. The backend's contract is `backend/docs/api/*.md` (generated) and the dev API's `/openapi.json`. `NEXT_PUBLIC_API_MOCKING=partial` sends everything to the dev API except the modules listed in `unbuiltHandlers` (`src/mocks/handlers/index.ts`).

### 9.1 Connected to the real backend

| Area | Data IDs | Endpoints |
|---|---|---|
| Sign-in, session, refresh, sign-out | AUTH-001…006 | `/auth/login`, `/auth/otp/*`, `/auth/refresh`, `/auth/logout`, `/auth/me` |
| Lead list — cursor paging in the URL, stage / source / type filters, search | LEAD-001 | `GET /leads` |
| New lead — territory picker, admin lookups, safe retries, field errors | LEAD-002 | `POST /leads` |
| Lead page — the real record and possible duplicates | LEAD-003 | `GET /leads/{id}` |
| Lead count — sidebar badge and Sales tab, exact | LEAD-004 | `GET /leads/stats` |
| Lookups — sources, irrigation systems, lost reasons, territories | MSTR-002 | `/lookups/*`, `/territories` |
| Lead history and notes — the Activity card on the lead page | LEAD-005, LEAD-006 | `GET /leads/{id}/timeline`, `POST /leads/{id}/notes` |
| Stage change and reopen — Update stage menu, lost reason, won and reopen dialogs | LEAD-007 | `POST /leads/{id}/transition`, `POST /leads/{id}/reopen` |
| Assign owner and channel partner | LEAD-008 | `POST /leads/{id}/assign`, `GET /leads/assignees`, `GET /lookups/partners` |
| Quotations list — the Quotations page and a lead's quotations | QUOT-001 | `GET /quotations` |
| Quotation detail — the document as printed, with its notices | QUOT-002 | `GET /quotations/{id}` |
| Open a quotation's PDF | QUOT-003 | `GET /quotations/{id}/pdf` |

LEAD-005…008 and QUOT-001…003 are built on the backend's contract and tested against the mock backend, which follows its rules. They go to the dev API in `partial` mode but have **not yet been checked there by hand** — do that before they reach staging.

**`/leads/summary` is gone.** It was a guessed contract the backend never served. The count first moved to `GET /leads?limit=1&include_total=true` (PR #8), then to `GET /leads/stats` (PR #18). The stats are not a one-to-one replacement:

| Old `/leads/summary` (guessed) | `GET /leads/stats` (real) |
|---|---|
| `total` | `total` — exact, never capped |
| `byStatus` | `by_stage` — the backend's nine stages |
| `bySource`, `byType` | not served |
| `followUpsDueToday` | not served — the backend records no follow-up date yet |
| — | `by_priority`, `unassigned` (new) |

### 9.2 Still mocked — no backend endpoint yet

| Area | Data IDs | Mock endpoints | Needs from the backend |
|---|---|---|---|
| Dashboard figures | RPT-001 | `GET /dashboard/overview` | A figures endpoint, or agreement to compose it from `/leads/stats` and `/orders/stats`; source breakdown; follow-ups |
| Notifications | NOTIF-001, NOTIF-002 | `GET /notifications`, `POST /notifications/read` | The endpoints |
| Staff messages | MSG-001…005 | `/conversations*`, `/staff-directory` | The endpoints |

### 9.3 Served by the backend, not yet built on the frontend

| Area | Endpoints | Contract | Order |
|---|---|---|---|
| **Quotations, the rest** — the builder (draft, lines, live pricing from `POST /pricing/quote-lines`, `rate_changed`); send and discount approval; accept, reject, negotiation (what moves a lead to quoted, negotiation and won); revise, versions, timeline, delete; the public `/q/{token}` page | `POST`/`PATCH`/`PUT`/`DELETE /quotations/*`, `POST /pricing/quote-lines`, `/public/q/*` | `backend/docs/handover/quotations-api-contract.md` | **1 — in progress** (reads done: QUOT-001…003) |
| Sales orders, approvals, dispatch | `/orders/*`, `/approvals/*`, `/dispatches/*` | `backend/docs/handover/orders-api-contract.md` | 2 |
| Lead edit, delete, duplicates queue, merge | `PATCH`/`DELETE /leads/{id}`, `/leads/duplicates`, `/leads/{id}/merge` | `backend/docs/api/leads.md` | 3 |
| Lead QR codes, public lead capture | `/lead-qr-codes`, `/public/*` | `backend/docs/handover/public-lead-capture-contract.md` | 4 |
| Products, price lists, tax rates, subsidy, users, org units, territories, partners (admin) | `/products`, `/price-lists`, `/tax-rates`, `/subsidy/*`, `/users`, `/org-units`, `/partners` | `backend/docs/api/*.md` | 5 |

**On `backend-foundation`, not yet in `integration`:** the tasks and planner contract (FS-014) and the complaints contract (FS-015).

### 9.4 Asked of the backend

Every open ask — sorting, a follow-up date, crops and land, win probability, territory levels, names in assignment events, stats by source, the dashboard, notifications and messages endpoints, the dev API — is a task with a checkbox in **[`docs/Backend-Tasks.md`](../../docs/Backend-Tasks.md)** (BE-001…). The backend developer ticks it and writes the commit and any notes there; the frontend reads it after each merge.

### 9.5 Housekeeping

- Dependabot PRs #13–#17 target `integration`. Three are major upgrades — ESLint 10, `@vitest/browser` 5, jsdom 30 — and need a look before they merge.
- PR #11, `integration` → `staging`, is open for the staging check ([Environments.md](Environments.md)).
- Consider generating the Zod contracts from `/openapi.json`, as the backend handover suggests, so a contract change fails the type check rather than a screen.

---

*Next revision after: side-by-side comparison with Loopify's internal week plan + client answers to [§Z](Docs/Open-Questions.md).*
