# Architecture — Polysil Irrigation CRM & Dealer Portal

> **Status:** DRAFT v0.1 — proposed, pending sign-off. Every choice here has a matching ADR in [Decisions.md](Docs/Decisions.md).
> Nothing in this document is implemented yet.

---

## 1. System context

**Three applications, one domain model.**

```
   ┌─ APP 1 · Internal CRM ─────────────┐   ┌─ APP 2 · Dealer / Customer Portal ─┐
   │  Management · RM/AM · Sales Mgr    │   │  Distributor · Dealer · Sub-dealer │
   │  Sales Exec · Marketing · Accounts │   │  Agent · Customer/Farmer           │
   │  Quality · Support · Admin         │   │                                    │
   └────────────────┬───────────────────┘   └──────────────┬─────────────────────┘
                    │        Next.js — route groups        │
                    └──────────────────┬───────────────────┘
                                       │
                          ┌────────────┴────────────┐
                          │   src/server/services   │  ← the real contract
                          └────────────┬────────────┘
                    ┌──────────────────┴──────────────────┐
                    │                                     │
           Server Components /                       /api/v1  (REST)
           Server Actions                                 │
                                       ┌─────────────────┴──────────────────┐
                                       │  APP 3 · Field Sales App (Expo)    │
                                       │  Sales Executive · Sales Manager   │
                                       │  one binary, role-based screens    │
                                       └────────────────────────────────────┘
                                       │
        ┌──────────────┬───────────────┼───────────────┬──────────────┐
        ▼              ▼               ▼               ▼              ▼
   WhatsApp       Meta Lead Ads     SMS (DLT)       Email        ERP / Tally
   Cloud API      webhook            MSG91          Resend        (TBD — Q9)
```

**Apps 1 and 2 are route groups in a single Next.js codebase** ([ADR-001](Docs/Decisions.md)) — `(crm)` and `(portal)`. They are separate *applications* to users and separate *route groups* to us. They share an identical domain model; splitting them into separate deployments would triple the contract surface for no benefit. Route-group middleware enforces strict audience separation: a dealer must never resolve a `(crm)` route.

**App 3 is one Expo app, not two** ([ADR-017](Docs/Decisions.md)). A Sales Manager gets extra screens and wider data scope through the same role system that governs the web — resolved at launch, driving navigation. Manager-only analytics screens are lazy-loaded.

**Customer/Farmer sits inside App 2** by the client's grouping. A farmer and a distributor share almost nothing in navigation, vocabulary, or data — so it is a distinct lightweight OTP experience within the same codebase, not the dealer interface with fields hidden. Scope pending [Q31](Docs/Open-Questions.md).

**`/api/v1` is a Week 1 frozen deliverable**, not a later addition — the mobile track opens in Week 3 and cannot build against an unfrozen API. Both the web and the mobile app call the same service layer; the HTTP layer is a thin adapter, never a second home for business logic.

---

## 2. Stack

| Layer | Choice | ADR |
|---|---|---|
| Framework (web) | Next.js 15 (App Router), React 19, TypeScript strict | ADR-001 |
| Framework (mobile) | React Native via **Expo** (SDK 54+), TypeScript strict, expo-router | ADR-017 |
| Mobile location | `expo-location` foreground + background task; `expo-task-manager` | ADR-017 |
| Mobile offline | SQLite (`expo-sqlite`) queue + sync on reconnect | ADR-017 |
| Mobile distribution | EAS Build → internal (signed APK / Managed Google Play) | ADR-018 |
| Styling | Tailwind CSS v4 · shadcn/ui (Radix primitives, owned source) | ADR-007 |
| Animation | Framer Motion (`motion`), reduced-motion respected | ADR-007 |
| Database | Supabase Postgres, region `ap-south-1` (Mumbai) | ADR-002 |
| Auth | Supabase Auth — email/password (staff), phone OTP via MSG91 (channel + consumers) | ADR-003 |
| Authorization | Postgres RLS + closure-table hierarchy scoping | ADR-004 |
| Data access | Server Components (reads) + Server Actions (writes) over a shared service layer | ADR-005 |
| Client state | TanStack Query (tables), nuqs (URL state), react-hook-form + Zod | ADR-006 |
| Tables | TanStack Table v8 headless + shadcn shell | ADR-007 |
| i18n | next-intl — `en`, `hi`, `gu` | ADR-008 |
| Messaging | WhatsApp Cloud API (direct, no BSP) · MSG91 SMS · Resend email | ADR-009 |
| Files | Supabase Storage (docs, complaint photos, visit photos) | ADR-010 |
| Scheduling | Supabase `pg_cron` + Edge Functions (reminders, SLA breach, rollups) | ADR-011 |
| PDF | `@react-pdf/renderer` server-side (no Chromium on serverless) | ADR-012 |
| Testing | Vitest (services, GST engine, scoring) · Playwright (12 critical flows) | ADR-013 |
| Observability | Sentry · Vercel Analytics · Postgres slow-query log | ADR-014 |
| Hosting | Vercel (Mumbai edge) + Supabase Mumbai | ADR-015 |

**Why this stack for *this* client:** every component is either open-source or self-hostable (Supabase, Next.js, shadcn, Postgres). A crores-valuation client asking "what happens if a vendor changes terms?" gets a real answer: the database is plain Postgres, the UI components are in our repo, the app runs anywhere Node runs. No proprietary query language, no vendor-locked auth, no closed component library.

---

## 3. Repository layout

```
polysil/
├── Docs/                        # this folder — the contract
├── supabase/
│   ├── migrations/              # ordered SQL, single source of schema truth
│   ├── seed/                    # Gujarat territory data, demo SKUs, demo dealers
│   └── functions/               # Edge Functions (cron jobs, webhooks)
├── src/
│   ├── app/
│   │   ├── (crm)/               # internal CRM — staff roles only
│   │   ├── (portal)/            # dealer / sub-dealer / agent
│   │   ├── (consumer)/          # public relationship portal
│   │   └── api/
│   │       ├── webhooks/        # whatsapp, meta-leads, payment
│   │       └── public/          # website enquiry form intake
│   ├── contracts/               # ⛔ FROZEN LAYER — Zod schemas, enums, DTOs
│   │   ├── lead.ts  quote.ts  order.ts  complaint.ts  …
│   │   └── index.ts
│   ├── server/
│   │   ├── db/                  # ⛔ FROZEN — generated types, client factories
│   │   ├── services/            # ⛔ FROZEN SIGNATURES — all business logic
│   │   │   ├── lead.service.ts  gst.service.ts  audit.service.ts …
│   │   └── integrations/        # whatsapp/, sms/, email/ — behind interfaces
│   ├── components/
│   │   ├── ui/                  # ⛔ FROZEN — design system primitives
│   │   ├── data-table/          # the one table used everywhere
│   │   └── <feature>/           # feature components (free layer)
│   ├── lib/                     # rbac, hierarchy, formatting, i18n config
│   └── messages/                # en.json, hi.json, gu.json
├── mobile/                      # APP 3 — Expo field sales app
│   ├── app/                     # expo-router; role-gated route groups
│   ├── src/
│   │   ├── api/                 # generated client for /api/v1 — never hand-written
│   │   ├── offline/             # SQLite queue + sync engine
│   │   └── location/            # background task, permissions, consent gate
│   └── eas.json                 # internal distribution profiles
├── e2e/                         # Playwright critical flows (web)
└── tests/
    ├── rbac-matrix/             # GENERATED from Docs/RBAC.md — do not hand-edit
    ├── scenarios/               # Testing.md §5 suites
    └── seed/                    # demo + scale profiles
```

**⛔ FROZEN** means: only Opus 5 or Nakul modifies these, only via an ADR. Feature agents read them and never write them. This is the mechanism that keeps four models from producing four architectures.

---

## 4. Domain model (core entities)

Full ERD to be produced Week 1 D1. The spine:

```
territory (state → district → taluka)
    │
org_unit ── user ── role                    # Management → RM → SM → Executive
    │
channel_partner ─────────────────────┐      # depot|distributor|dealer|sub_dealer|agent
    │  parent_id (self-ref, closure)  │      # institutional is a partner_type too
    │                                 │
customer ◀── lead ──▶ lead_source     │      # consumer / farmer / institution
    │         │                       │
    │         ├── lead_score          │
    │         ├── duplicate_link      │      # REQ-107, REQ-108
    │         └── won_lost_reason     │
    │                                 │
    ├── quotation ── quotation_line ──┤      # GST computed per line
    │       └── quotation_event       │      # sent/viewed/accepted/…
    │                                 │
    ├── sales_order ── order_line ────┘
    │       └── dispatch
    │
    ├── payment ── payment_allocation         # advance / balance / settlement
    ├── subsidy_claim                         # tracked separately from payment
    ├── complaint ── complaint_event ── sla_timer
    │       └── quality_assessment ── refund_request
    ├── warranty
    ├── rating
    └── activity_event  ◀── every module writes here (REQ-901, the 360° view)

scheme ── scheme_territory ── scheme_product   # geo-scoped discounts
product ── price_list_item (per channel tier)
task · visit · mom · approval_request · notification · audit_log
```

**Three modelling decisions worth flagging early:**

1. **`activity_event` is the 360° view.** Every module emits an append-only event (`entity_type`, `entity_id`, `customer_id`, `occurred_at`, `actor`, `payload`). The timeline is one indexed query, not ten joins. This also gives REQ-902 (drop-off point) almost for free — it's a gap analysis over one ordered table.
2. **Channel hierarchy is a self-referencing tree with a closure table.** Recursive CTEs inside RLS policies on every request would be too slow. A maintained closure table (`ancestor_id`, `descendant_id`, `depth`) makes "can this user see this row?" a single indexed lookup. This is the highest-risk piece of the schema — it's what makes REQ-704 work at all.
3. **Money is `numeric(14,2)`, never float.** GST rounding is per-line, half-up, per Indian convention. The GST engine is a pure function with its own unit-test suite — it is the one place a bug becomes a legal problem.

---

## 5. Authorization model

Two orthogonal scopes, both enforced in the database:

| Scope | Question | Mechanism |
|---|---|---|
| **Hierarchy scope** | *Which rows?* | RLS using the closure table — a Sales Manager sees rows owned by any descendant org_unit; a Dealer sees only their own subtree |
| **Permission scope** | *Which actions?* | `role_permission (role, module, action)` — action ∈ view/create/edit/approve/delete, seeded from [RBAC.md](Docs/RBAC.md) |

**Non-negotiable:** the UI hiding a button is not authorization. Every mutation is checked by RLS. The UI check exists only so the user isn't shown a control that will fail. Both layers read the same `role_permission` table, so they cannot drift.

**Audit (REQ-1302/1303):** a single generic Postgres trigger on every business table writes `audit_log (actor, action, table, row_id, old_jsonb, new_jsonb, at)`. Written as a trigger, not application code — application code can be bypassed by a service-role client or a direct SQL fix; a trigger cannot. `audit_log` has no UPDATE or DELETE policy for any role, and a `REVOKE` on those grants. That is what "cannot be tampered with" actually means.

---

## 6. Integrations

| Integration | Direction | Notes | Failure mode |
|---|---|---|---|
| WhatsApp (via client's BSP) | out + in (webhook) | Behind a provider port ([ADR-020](Docs/Decisions.md)). 12 templates; 24-hour session window; opt-in consent stored per contact. **BSP not yet named - [Q36](Docs/Open-Questions.md)** | Queue + retry; fall back to SMS |
| MSG91 SMS | out | DLT-registered templates only; used for OTP + reminders | Retry, then email |
| Resend | out | Transactional email on verified domain (SPF/DKIM) | Logged, non-blocking |
| Meta Lead Ads | in (webhook) | P2 — requires `leadgen_retrieval` App Review | N/A until P2 |
| Website enquiry form | in | Public rate-limited endpoint, HMAC-signed, Zod-validated | 429 + captcha |
| ERP | future, two-way | **ERP is planned, not live.** We build *seams*, not a sync engine ([ADR-019](Docs/Decisions.md)). Vendor unknown — [Q37](Docs/Open-Questions.md) | N/A in Phase 1 |
| Payment gateway | ? | **Undefined — Q8.** Currently modelled as payment *records*, not collection | N/A |

**All integrations sit behind an interface** (`src/server/integrations/whatsapp/provider.ts` etc.) with a mock implementation. This is what lets us build and test REQ-601..604 in Week 2 while Meta verification is still pending — the module is complete and demoable against the mock, and going live is a config change.

---

## 7. Scale, concurrency & load

**Confirmed by client (2026-08-14):** ~700-800 named users, **>=100 concurrent**. This is not a large system by Postgres standards, but it is comfortably past the point where naive patterns fall over. Treated as a first-class constraint, not a later optimisation.

### 7.1 Load model

| Dimension | Phase 1 target | Design headroom |
|---|---|---|
| Named users | 700-800 | 2,000 |
| Concurrent sessions | 100 sustained | **300 peak** - see 7.4 |
| Channel partners | 500-3,000 | 10,000 |
| Customers / farmers | 50k-500k over 3 years | 1M |
| Activity events | 500k+ | 5M |
| Report p95 | < 2s at scale seed | asserted in CI |
| API p95 | < 400ms | asserted in load test |
| Mobile sync burst | 100 devices flushing queues at end-of-day | jittered + batched |

### 7.2 The four things that actually break at this scale

Named explicitly, because each has a specific and non-obvious mitigation.

**1. Connection exhaustion - the most likely failure.**
Vercel serverless functions each hold a Postgres connection. 100 concurrent users spread across many function instances will exhaust `max_connections` long before CPU is stressed. All application traffic goes through **Supavisor in transaction mode**. The consequence is binding: no session-scoped state - no `SET` outside a transaction, no session-level advisory locks, prepared statements handled in the driver's transaction-safe mode. This is an architectural constraint on every service, not a config toggle ([ADR-021](Docs/Decisions.md)).

**2. RLS is evaluated per row.**
An RLS policy runs for **every candidate row**. A policy containing an uncached subquery over the closure table turns a 500k-row scan into 500k subqueries. Mandatory discipline in every policy:

- Wrap auth calls in a scalar subselect - `(SELECT auth.uid())`, never bare `auth.uid()`. Postgres then evaluates it once as an InitPlan instead of once per row. The difference is orders of magnitude, not percent.
- Helper functions are `STABLE SECURITY DEFINER`; the accessible-territory set resolves once per statement.
- **Every column referenced in a policy is indexed.** No exceptions.
- Policy performance is asserted at `scale` seed volume in CI, not eyeballed.

This is why the channel hierarchy is a **closure table** and not a recursive CTE ([ADR-004](Docs/Decisions.md)). At 100 concurrent users that choice stops being academic.

**3. Reports and dashboards.**
Ten reports over 500k+ rows with 100 concurrent users is the classic collapse point. Reports read **materialized views** refreshed by `pg_cron`, never live aggregation over raw tables. Dashboard widgets are cached with an explicit staleness contract shown in the UI ("as of 14:05") rather than pretending to be live.

**4. Realtime vs polling.**
Supabase Realtime is used **narrowly** - notifications and complaint escalations only. List views and dashboards use TanStack Query with a deliberate `staleTime`, not live subscriptions. 100 concurrent websocket subscribers multiplied across channels is a cost and a failure mode we take on only where the product genuinely needs it.

### 7.3 Client-side constraints (unchanged, still binding)

- Dealer portal traffic is **low-end Android on 3G/4G in rural Gujarat**. Hard budget: < 200KB JS on first load, server-rendered tables, no client-side data grids on the dealer side.
- Timeline query (REQ-901) is the hottest read - composite index on `(customer_id, occurred_at desc)`.
- Mobile end-of-day sync is a **burst**, not steady state. Sync is batched, jittered, and idempotent by client-generated UUID.

### 7.4 Seasonality - why headroom is 3x, not 1.2x

Irrigation sales in Gujarat are strongly seasonal: pre-monsoon demand, and subsidy-deadline crunches. "100 concurrent" is an average, and averages are the wrong number to size against. A subsidy application deadline plausibly puts every field executive and a large share of dealers on the system within the same two hours. We design and load-test to **300 concurrent** so that the seasonal peak is boring rather than an incident.

### 7.5 Infrastructure implication

Supabase Free/Nano is not viable for production at this load - the connection ceiling alone rules it out. Production needs a paid instance sized for the pooler and for materialized-view refresh, with PITR enabled. This is a **client cost line item**, flagged now rather than discovered in Week 6 ([Q38](Docs/Open-Questions.md)).

---

## 8. Environments

| Env | Branch | Database | Purpose |
|---|---|---|---|
| Local | any | local Supabase (Docker) | development |
| Preview | per-PR | shared staging DB, seeded | client clicks each feature the day it's built |
| Staging | `main` | staging DB, seeded with realistic Gujarat data | Friday demos + UAT |
| Production | `release` tag | production DB, ap-south-1, PITR enabled | live |

Secrets live in Vercel + Supabase only. Never in the repo, never in `Docs/`. `.env.example` is committed with keys and empty values.

---

## 9. Known architectural gaps (deliberately open)

1. **Stock ownership (Q9)** — if Tally is the source of truth, `product_stock` becomes a synced read model with a reconciliation job, and REQ-1101/1103/1105 change materially. Held open until answered.
2. **Invoicing (Q12)** — if e-invoice/IRN + e-way bill are in scope, that is an integration with the GSTN IRP and roughly a week of work not currently in the plan.
3. **Offline capability** — rural field usage may need offline visit logging with sync. Not currently scoped. Flagged as Q23.
4. **Native apps** — background location (REQ-702) is impossible in a PWA on iOS and unreliable on Android. Expo app is Phase 2 by design, not by omission.

---

## 10. System-of-record ownership (ERP-forward)

The client is planning an ERP and wants it synced with the CRM. The ERP **does not exist yet**, so Phase 1 builds no connector. What it does build is the part that is expensive to retrofit: a written answer to *which system owns which entity*, and the columns needed to reconcile later.

The failure this prevents is the two-master problem - two systems both believing they own product pricing, and the disagreement surfacing after 200k rows exist ([ISS-015](Docs/Issues.md)).

| Entity | Phase 1 owner | Likely owner once ERP lands | Sync direction |
|---|---|---|---|
| Product master, HSN, UoM | CRM | **ERP** | ERP -> CRM (read model) |
| Price lists, tier pricing | CRM | **ERP** | ERP -> CRM |
| Stock / inventory | CRM (manual) | **ERP** | ERP -> CRM |
| Customer / farmer master | **CRM** | CRM | CRM -> ERP |
| Channel partner master | **CRM** | CRM | CRM -> ERP |
| Lead, activity, visit, task | **CRM** | CRM | none (CRM-only) |
| Quotation | **CRM** | CRM | CRM -> ERP |
| Sales order | **CRM** | contested - decide before ERP | CRM -> ERP |
| Tax invoice, e-invoice/IRN, e-way bill | *(out of Phase 1 scope)* | **ERP** | ERP -> CRM (status only) |
| Payment / receipt | CRM (records only) | **ERP** | ERP -> CRM |
| Scheme, campaign, reward | **CRM** | CRM | CRM -> ERP (as discounts) |

**This table is a proposal, not a decision.** It needs client sign-off ([Q39](Docs/Open-Questions.md)) before the Week 1 schema freeze, because ownership determines which tables get sync columns and which get write constraints.

### What Phase 1 actually builds for this - roughly 1 day

1. **Identity columns on every syncable entity:** `external_id text`, `source_system text`, `synced_at timestamptz`, with a partial unique index on `(source_system, external_id)`. Adding columns to an empty table is free; backfilling identity mapping across 500k live rows later is a project.
2. **`sync_outbox` table** written by the same trigger mechanism as `audit_log` - every insert/update/delete on a syncable entity appends a change event. Without it a future integration is reduced to full-table diffs; with it, it is a queue consumer.
3. **Idempotency keys** on all mutating service methods - needed for mobile offline sync regardless, so the ERP gets them free.
4. **All writes through `src/server/services`** - already the contract. A future ERP sync becomes another caller of existing services, not a second write path into the database.

What Phase 1 deliberately does **not** build: a connector, an ETL, field mappings, or conflict-resolution rules for a system whose vendor is unknown. That is speculative work against an unknown API shape ([ADR-019](Docs/Decisions.md)).

---

*Every open item above is tracked in [Open-Questions.md](Docs/Open-Questions.md).*
