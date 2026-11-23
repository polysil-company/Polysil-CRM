# Decisions — Architecture Decision Record (ADR) Log

Append-only. Anyone (human or model) may append a `PROPOSED` ADR. Only Nakul moves an ADR to `ACCEPTED`. A `SUPERSEDED` ADR is never deleted — the reasoning is the point.

**Format:** Context → Decision → Alternatives considered → Consequences. If you cannot name a real alternative you rejected, you have not made a decision — you have made an assumption.

| Status | Meaning |
|---|---|
| `PROPOSED` | Written, not yet approved. Do not build on it. |
| `ACCEPTED` | Binding. Changing it requires a new superseding ADR. |
| `SUPERSEDED` | Replaced. Kept for history. |
| `REJECTED` | Considered and declined. Kept so it is not re-proposed. |

---

## ADR-001 — Single Next.js app with route groups, not a monorepo
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Context.** Four audiences (CRM, dealer portal, consumer portal, field PWA) share one domain model. A Turborepo with separate apps is the "proper" answer at scale.

**Decision.** One Next.js 15 App Router application. Audiences separated by route groups: `(crm)`, `(portal)`, `(consumer)`. Shared contracts live in `src/contracts`, not a published package.

**Alternatives.** (a) Turborepo with `apps/crm`, `apps/portal`, `packages/contracts` — correct at 6+ months, but adds build orchestration, versioning and duplicate config in a 5-week window. (b) Separate repos — rejected outright; the contract would drift immediately.

**Consequences.** One deploy, one env set, one CI pipeline. Route-group middleware must strictly enforce audience separation — a dealer must never resolve a `(crm)` route. Extraction to a monorepo remains possible later because `contracts` and `services` are already isolated folders.

---

## ADR-002 — Supabase Postgres as the primary datastore
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Context.** The domain is deeply relational (hierarchies, ledgers, orders, audit) and the BRD demands ten aggregate reports and a tamper-proof audit trail.

**Decision.** Supabase Postgres, region `ap-south-1` (Mumbai). RLS for authorization, triggers for audit, materialized views for reports, `pg_cron` for scheduling.

**Alternatives.** (a) **Convex** — excellent DX and realtime, but the reporting requirement (10 aggregate reports, ad-hoc filters, exports) wants SQL, and the audit requirement wants database triggers. (b) **Firebase/Firestore** — document model fights a ledger-and-hierarchy domain; aggregate reporting becomes application code. (c) **Prisma + a plain Postgres host** — loses RLS integration, auth, storage and cron as one package, costing setup days we do not have.

**Consequences.** Authorization logic lives in SQL, which is harder to unit test and demands an RLS test suite (Week 1). In exchange: no vendor lock-in of consequence — it is standard Postgres, self-hostable, `pg_dump`-portable. Mumbai region also satisfies DPDP Act data-residency expectations.

---

## ADR-003 — Dual auth: email/password for staff, phone OTP for channel & consumers
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Context.** Dealers, sub-dealers, agents and farmers in rural Gujarat are mobile-number identities. Many will not have or use email. Internal staff are the opposite.

**Decision.** Supabase Auth. Email/password + optional TOTP for staff. Phone OTP via **MSG91** for channel partners and consumers. One `users` table, a `auth_method` discriminator, role assigned at invite time.

**Alternatives.** (a) Phone OTP for everyone — poor fit for desk staff and weaker for admin accounts. (b) Twilio for OTP — significantly more expensive for Indian volumes and still requires DLT. (c) Supabase's built-in SMS providers — poor India coverage/pricing.

**Consequences.** Requires TRAI **DLT registration** (client-side, 5–15 working days) before OTP works in production — a Week 0 blocker (see Q6). Mock OTP in dev/staging until then.

---

## ADR-004 — Authorization via Postgres RLS + a hierarchy closure table
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Context.** REQ-704 requires each hierarchy level to see exactly its own subtree, across ~20 tables. The BRD explicitly forbids undefined or default access.

**Decision.** Two-layer model: **row scope** via RLS reading a maintained closure table (`ancestor_id`, `descendant_id`, `depth`); **action scope** via a `role_permission (role, module, action)` table seeded from `Docs/RBAC.md`. Both the UI guard and the RLS policy read the same permission table.

**Alternatives.** (a) Recursive CTE in each policy — correct but re-walks the tree on every row check; unacceptable on list queries. (b) `ltree` path column — fast, but reparenting a distributor rewrites every descendant path. (c) Application-layer authorization only — rejected: bypassable, and unauditable.

**Consequences.** Closure table must be maintained by trigger on partner insert/reparent, and needs its own tests. Reparenting is an O(subtree) write — acceptable, it is rare. This is the highest-risk element of the schema and is built and tested first, in Week 1.

---

## ADR-005 — Server Components + Server Actions over a shared service layer; REST only for mobile
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Context.** A Phase 2 Expo app will need an HTTP API. Building REST endpoints now for a web app that does not need them is duplicated surface.

**Decision.** All business logic lives in `src/server/services/*`. The web app calls services directly from Server Components (reads) and Server Actions (writes). A thin `/api/v1/*` layer calls the *same* services for the mobile app. The **service layer is the contract**, not the HTTP layer.

**Amendment 2026-08-14:** the Field Sales App moved from Phase 2 into Phase 1, so `/api/v1` is now a **Week 1 deliverable** and part of the frozen contract layer, not a later addition. The mobile track cannot open in Week 3 against an unfrozen API.

**Alternatives.** (a) REST-first for everything — doubles the boilerplate and gives up RSC's data-fetching advantages. (b) tRPC — good, but redundant alongside Server Actions and adds a dependency for a benefit we get from typed actions.

**Consequences.** Services must never import React or Next request context — they take explicit `actor` and input arguments. This is what makes them reusable from cron jobs, webhooks and the future mobile API.

---

## ADR-006 — react-hook-form + Zod, TanStack Query, nuqs
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Decision.** Forms: react-hook-form + `zodResolver`, schema imported from `src/contracts`. Client tables: TanStack Query. Filters/pagination/sort: `nuqs` (URL as state) so every filtered view is shareable — which matters when a manager sends a subordinate "this list".

**Alternatives.** Redux/Zustand for server data — rejected; server state is not client state. Local component state for filters — rejected; loses shareable URLs and breaks back-button behaviour.

---

## ADR-007 — shadcn/ui + Tailwind v4 + TanStack Table + Framer Motion
**Status:** PROPOSED · 2026-08-14 · Nakul + Opus 5

**Decision.** shadcn/ui (source-owned Radix primitives) as the base, extended into a Polysil design system in `src/components/ui`. TanStack Table headless for all grids. Framer Motion for motion.

**Alternatives.** (a) MUI / Ant Design — fast to start, but produces exactly the generic enterprise look this client should not get, and fights Tailwind. (b) Fully custom primitives — accessibility work we cannot afford to redo in 5 weeks. (c) AG Grid — powerful, but heavy and licence-encumbered for the features we would want.

**Consequences.** We own the component source, so no upgrade risk and full visual control. Accessibility comes from Radix rather than from our own effort.

---

## ADR-008 — next-intl for en/hi/gu
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Decision.** `next-intl` with locale segment routing. English complete at launch; Hindi and Gujarati keys wired from Week 1, content supplied by the client (Q22).

**Consequences.** Every user-facing string must be a key from Day 1 — retrofitting i18n over 60 screens in Week 5 is a guaranteed failure. Gujarati typography needs a font with proper Gujarati coverage (Noto Sans Gujarati) and generous line-height; verify at 360px.

---

## ADR-009 — WhatsApp Cloud API direct, no BSP
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Context.** Options are Meta's Cloud API directly, or a BSP (Gupshup, AiSensy, Interakt, 360dialog, Twilio).

**Decision.** Meta Cloud API directly, behind our own provider interface.

**Alternatives.** BSPs offer a faster onboarding path and a ready inbox UI, at a per-conversation markup and with vendor lock-in on conversation history. Given REQ-604 requires our *own* dashboard tied to CRM records, we would be paying for an inbox we then rebuild.

**Consequences.** We handle template submission, the 24-hour session window, webhook verification and retry logic ourselves. Meta Business verification becomes a hard Week 0 dependency (Q4). The provider interface means switching to a BSP later is a one-file change if verification stalls.

---

## ADR-010 — Supabase Storage for files
**Status:** PROPOSED · 2026-08-14 · Opus 5
**Decision.** Complaint photos, visit photos, quote PDFs, promo material in Supabase Storage with RLS-backed buckets and signed URLs. Cloudinary reconsidered only if heavy image transformation becomes a need.

---

## ADR-011 — Scheduling via pg_cron + Edge Functions
**Status:** PROPOSED · 2026-08-14 · Opus 5
**Decision.** Reminders, SLA breach detection, scheme expiry and report rollups run on `pg_cron` invoking Supabase Edge Functions.
**Alternatives.** Vercel Cron — limited frequency on lower tiers and no DB-local context. Inngest/Trigger.dev — better DX and observability; revisit if job complexity grows beyond simple schedules.

---

## ADR-012 — PDF via @react-pdf/renderer
**Status:** PROPOSED · 2026-08-14 · Opus 5
**Decision.** Server-side React → PDF for quotations and report exports.
**Alternatives.** Puppeteer/Playwright HTML→PDF gives pixel-perfect fidelity but needs a Chromium binary that does not fit serverless comfortably. Rejected for the 5-week window.

---

## ADR-013 — Vitest + Playwright, with named critical flows
**Status:** PROPOSED · 2026-08-14 · Opus 5
**Decision.** Vitest unit tests are **mandatory** for: GST calculation, lead scoring, duplicate detection, hierarchy scoping, RLS policies, ledger arithmetic, SLA computation. Playwright covers 12 named critical flows (login per role, lead→won, quote→PDF, dealer order, complaint→refund, audit visibility, …).
**Consequences.** We do not chase coverage percentage. We cover the places where a bug costs money, access or legal standing.

---

## ADR-014 — Sentry from Week 1
**Status:** PROPOSED · 2026-08-14 · Opus 5
**Decision.** Sentry on both server and client from the first deploy, with PII scrubbing configured before any real data exists.

---

## ADR-015 — Vercel + Supabase, both Mumbai
**Status:** PROPOSED · 2026-08-14 · Opus 5
**Decision.** Vercel hosting, Supabase `ap-south-1`. PITR backups enabled on production before go-live.
**Consequences.** Data residency in India supports DPDP Act positioning. Self-hosting remains viable later since both layers are standard Node + Postgres.

---

## ADR-016 — Tests are the delivery gate; code review is narrowed to the contract layer
**Status:** PROPOSED · 2026-08-14 · Nakul + Opus 5

**Context.** What the client values is that functionality is correct and the application does not break under real scenarios. Line-by-line review of implementation code is a poor instrument for that — it reliably catches style and structure, and unreliably catches behaviour under edge conditions. It was also the throughput ceiling on a 5-week plan: one architect can carefully review ~60k lines in the window, against a ~130k-line system.

**Decision.** Implementation code is **not** reviewed line by line. A requirement ships when its acceptance suite passes CI. Human review is narrowed to the layer where tests structurally cannot reach: migrations, Zod contracts, service signatures, `rbac.ts` / `hierarchy.ts`, RLS policies, and the RBAC matrix — roughly 2–3k lines.

**This only holds because of four compensating mechanisms**, and the decision is void without them:
1. **Acceptance criteria authored before implementation**, from the requirement — the test spec never derives from the code.
2. **Adversarial pairing** — a different model writes the tests than writes the feature ([ISS-012](Docs/Issues.md)).
3. **Mutation testing** on business logic — proves tests detect breakage rather than merely executing lines.
4. **Generated RBAC test matrix** — ~1,400 role × table × operation assertions including negatives, which nobody writes by hand.

**Alternatives.** (a) Full line-by-line review — highest confidence per line, but caps throughput and still misses runtime edge behaviour. (b) Review *and* full testing — ideal in an unbounded schedule; here it buys less than the tests alone and costs the timeline. (c) Testing with no review at all — rejected: a wrong table relationship or a leaky RLS policy passes every functional test and surfaces as a rebuild in month three ([ISS-013](Docs/Issues.md)).

**Consequences.** The Definition of Done stops being advisory and becomes the entire quality system — a skipped checklist item is a shipped defect with nothing behind it. Test authorship costs roughly +25% agent time per feature. In exchange, the review ceiling disappears and correctness becomes *executable and repeatable* rather than dependent on one person's attention on one afternoon.

---

## ADR-017 — One Expo app for both field roles, not two
**Status:** PROPOSED · 2026-08-14 · Opus 5

**Context.** The BRD describes a "Location Tracking Sales App" and a separate "Sales Manager App". The client has since confirmed one Field Sales App used by Sales Executives and Sales Managers.

**Decision.** A single React Native / Expo application. Managers get additional screens and wider data scope through the **same role system that already governs the web** — not a second binary. Manager-only analytics screens are lazy-loaded so an executive never pays for them.

**Alternatives.** Two separate apps — two codebases, two build pipelines, two distribution channels and two review cycles, to serve users who overlap heavily in practice (managers are field-active too). Rejected as pure duplication.

**Consequences.** Role resolution must happen at launch and drive navigation, so a demoted or promoted user gets the right app on next login rather than requiring reinstall. This is exercised by the same generated permission matrix used on the web.

---

## ADR-018 — Internal distribution for the field app, not public app stores
**Status:** PROPOSED · 2026-08-14 · Opus 5 · **pending [Q29/Q30](Docs/Open-Questions.md)**

**Context.** REQ-702 requires background location. Google Play reviews the background-location permission **separately** from the app, requires a justification video, and routinely takes 2+ weeks with rejections. Apple scrutinises `always` location comparably. That single review could outlast the entire build ([ISS-011](Docs/Issues.md)).

**Decision.** Distribute internally — signed APK, Play Internal App Sharing, or Managed Google Play. Field staff are employees, not the public; there is no reason for a public listing.

**Alternatives.** Public Play Store listing — needed only if the app must be discoverable, which it must not. Rejected: it imports a multi-week external review into the critical path for zero benefit.

**Consequences.** No store review, no background-location review, and we control release timing entirely. Requires client Play Console or MDM access (Week 0 item 0.7). If iPhones are in the fleet, iOS needs TestFlight or Apple Business Manager and the mobile track roughly doubles — hence Q29.

---

## ADR-019 - ERP integration: build seams now, not a sync engine

**Status:** PROPOSED - 2026-08-14 - supersedes the open question behind D-B

**Context.** The client is planning an ERP and wants it synced with CRM data. The ERP does not exist yet: no vendor, no schema, no API. Two failure modes are available to us. Build nothing ERP-aware, and later face a migration that touches every table plus an identity backfill across hundreds of thousands of live rows. Or build a speculative integration layer against an imaginary API, and throw it away when the real vendor is chosen.

**Decision.** Build **integration seams**, not integration. Specifically, in Week 1:

1. A written system-of-record ownership table, signed off before schema freeze ([Architecture.md section 10](Docs/Architecture.md)).
2. `external_id` / `source_system` / `synced_at` on every entity that could plausibly become ERP-owned, with a partial unique index.
3. A `sync_outbox` change-event table, populated by the same trigger mechanism as `audit_log`.
4. Idempotency keys on every mutating service method - required for mobile offline sync anyway.
5. No direct database writes from feature code; every write goes through `src/server/services`.

No connector, no ETL, no field mappings, no conflict-resolution rules.

**Alternatives.**
- *Ignore the ERP until it exists.* Rejected. Retrofitting identity and change-capture onto a live 500k-row system is a multi-week project with a data-migration risk; doing it upfront on empty tables costs about a day.
- *Build a generic sync framework now.* Rejected. Every ERP has a different integration model - Tally is XML over a local HTTP port, SAP B1 is an OData Service Layer, Odoo is JSON-RPC, Zoho and Marg are different again. A generic layer built before the vendor is known will be wrong in ways we cannot predict, and it consumes Phase 1 capacity that has requirements waiting for it.

**Consequences.** Phase 1 cost is roughly one day. When the ERP arrives, integration becomes a bounded project - a queue consumer plus field mapping - rather than a schema migration. The ownership table becomes a contract the client has agreed to, which is what actually prevents the two-master problem ([ISS-015](Docs/Issues.md)).

**Consequence worth stating plainly:** if the ownership table puts tax invoicing with the ERP, then e-invoice/IRN and e-way bill compliance leave Phase 1 scope entirely. That is a material scope reduction and it needs to be confirmed, not assumed ([Q40](Docs/Open-Questions.md)).

---

## ADR-020 - WhatsApp behind a provider port; client's BSP is one implementation

**Status:** PROPOSED - 2026-08-14 - amends [ADR-009](Docs/Decisions.md)

**Context.** ADR-009 chose the WhatsApp Cloud API directly, accepting a 3-15 day Meta Business verification on the critical path. The client has since indicated they may already have a WhatsApp provider (a BSP) and can supply API access. That removes the verification lead time - genuinely good news - but replaces a documented, stable API with an unknown one. Indian BSPs vary widely: some are full API platforms, some are UI-first tools whose API is an afterthought, and some gate inbound webhooks behind higher plans.

**Decision.** All WhatsApp behaviour sits behind a `WhatsAppProvider` port in `src/server/integrations/whatsapp/`, with three implementations: `mock` (development and CI), `cloud-api` (direct Meta), and `<client-bsp>` (built once the provider is named). Feature code never touches a provider SDK.

**Alternatives.** Code directly against the client's BSP. Rejected: it couples 5 requirements to a vendor we have not evaluated, gives us nothing to develop against until credentials arrive, and makes a provider switch a rewrite rather than a config change.

**Consequences.** Roughly half a day of extra work. In exchange: REQ-601..605 are built and tested against the mock in Week 2 without waiting on the client, the BSP can be swapped without touching feature code, and if the BSP turns out to lack inbound webhooks we fall back to `cloud-api` without losing work.

**Still required from the client regardless of provider** - template approval is Meta's, not the BSP's, so the 12 template texts are still a Week 0 deliverable ([Q36](Docs/Open-Questions.md)).

---

## ADR-021 - Transaction-mode connection pooling, and RLS written for 100+ concurrent users

**Status:** PROPOSED - 2026-08-14

**Context.** Confirmed load is 700-800 named users with at least 100 concurrent, and a seasonal profile that will push peaks well above the average. Two specific things break first at this scale, and neither is caught by functional tests: Postgres connection exhaustion under serverless fan-out, and RLS policies that evaluate an uncached subquery per row.

**Decision.**
1. All application traffic goes through **Supavisor in transaction mode**. No session-scoped Postgres state anywhere in the codebase.
2. RLS policies follow a fixed discipline: auth calls wrapped in a scalar subselect, helper functions `STABLE SECURITY DEFINER`, every policy-referenced column indexed.
3. Reports read materialized views refreshed by `pg_cron`; no live aggregation over raw tables.
4. Supabase Realtime is used only for notifications and escalations, not for list views or dashboards.
5. A **load test at 300 concurrent** against the `scale` seed is a nightly CI gate, not a pre-launch afterthought.

**Alternatives.** Session-mode pooling, which preserves session state but caps concurrency far below our target. Rejected. Ship first and tune later - rejected because both mitigations are structural: transaction-mode compatibility and RLS shape cannot be retrofitted without rewriting every policy and auditing every service.

**Consequences.** A real constraint on how services are written, enforced in the frozen contract layer where it is cheap. Production requires a paid Supabase instance sized for this ([Q38](Docs/Open-Questions.md)) - a client cost line, surfaced now.

---

## Decisions still needed (not yet ADRs — see [Open-Questions.md](Docs/Open-Questions.md))

| # | Decision | Blocked on |
|---|---|---|
| D-A | Phase 1 / Phase 2 scope split, in writing, signed | Q1, Q2 |
| D-B | ~~ERP integration~~ - **resolved by [ADR-019](Docs/Decisions.md)**: seams now, connector later. Remaining: sign off the ownership table | Q39 |
| D-C | Invoicing in scope? e-invoice IRN + e-way bill? **Likely ERP-owned - would remove this from Phase 1** | Q12, Q40 |
| D-D | Online payment collection vs payment records only | Q8 |
| D-E | Field tracking: PWA check-in only vs native background tracking | Q21 |
| D-F | Lead scoring model — weights and thresholds | Q14 |
| D-G | Approval limits per role | Q16 |
| D-H | SLA matrix per complaint type | Q17 |
| D-I | Subsidy workflow — tracking only vs iKhedut/portal integration | Q18 |
| D-J | Reward tier qualification rules | Q19 |
