# Context Snapshot — Polysil CRM/DMS, as of 6 September 2026

> **What this file is.** A complete record of the project as it stands *before* the September pivot
> (backend developer joins, scope simplified, additions and removals). Everything below is
> **pre-pivot state**. It is written so that when scope changes, we can say precisely what changed,
> what survived, and what was thrown away — rather than reconstructing it from memory.
>
> **Documents last revised:** 2026-08-14 and 2026-08-17. **Snapshot taken:** 2026-09-06.
> There is a ~3 week gap between the last doc revision and this snapshot; decisions made in
> meetings during that gap are recorded in §7 but are **not yet reflected in the committed docs**.

---

## 1. Commercial shape

| | |
|---|---|
| **End client** | Polysil Irrigation — Indian micro-irrigation manufacturer (drip, sprinkler, mini-sprinkler) |
| **Contract holder** | Loopify Solutions |
| **Delivery** | Nakul Srivastava, solo, as architect/reviewer orchestrating multiple models |
| **Chain** | Nakul → Loopify → Polysil. **All client contact goes through Loopify.** No direct line to Polysil. |
| **Repo** | `imnakul/polysil-crm` — **private, client-confidential** |
| **Timeline** | 6.5 weeks ≈ 32 working days |
| **Scale** | ~700–800 named users, 100+ concurrent, designed to 300 |
| **Budget** | Fixed, already agreed before scope was fully understood |

**Confidentiality constraint in force:** secrets live in host/env only, never in the repo or `Docs/`.
`.gitignore` hard-blocks `.env*`, `*.pem`, `*.key`, `service-account*.json`.

---

## 2. What we are building — three applications

1. **Web Internal CRM** — Polysil staff. Leads → quotations → orders → dispatch → service → reports.
2. **Web Dealer / Customer Portal** — channel partners and farmers.
3. **Mobile Field Sales App** — Expo / React Native, for field sales staff.

**Apps 1 and 2 are one Next.js codebase**, separated by route groups `(crm)` and `(portal)`
(ADR-001). Splitting them "would triple the contract surface for no benefit." Route-group
middleware enforces audience separation.

**App 3 is one Expo app, not two** (ADR-017), distributed internally rather than through public
app stores (ADR-018).

---

## 3. Repository inventory at snapshot time

**There is no source code. The repo is documentation only.**

```
polysil-crm/
├── .gitignore
├── README.md
└── Docs/
    ├── AGENTS.md               ← the 10-layer contract model, layers 3–9 FROZEN
    ├── Acceptance-Criteria.md
    ├── Architecture.md         ← DRAFT v0.1
    ├── BRD-Source.txt          ← the signed BRD, verbatim
    ├── Decisions.md            ← ADR-001 … ADR-021
    ├── Documentation.md
    ├── Flowchart-Source.md     ← verbatim extract of the client's XLSX flowchart
    ├── Issues.md               ← ISS-001 … ISS-026
    ├── Learning.md
    ├── Open-Questions.md       ← Q1 … Q53, plus §Z kickoff shortlist
    ├── Plan.md                 ← DRAFT v0.2, revised v0.3 (2026-08-14)
    ├── Requirements.md         ← 73 requirements
    └── Testing.md
```

**Git state:** branch `main`, 4 commits.

```
96da1cb docs: client flowchart intake - 11-state subsidy scope, 8 new issues, 11 new questions
d062c04 docs: ERP seams, BSP-agnostic WhatsApp, and scale for 100+ concurrent
fb8a3be docs: shift to test-gated delivery, 3 apps, 6.5-week plan
0e1ac42 docs: establish contract-first project foundation
```

**One uncommitted change** — `Docs/Issues.md`, +4 / −2. ISS-022 retitled from *"Depot and
Institutional Sales are missing from the channel hierarchy"* to *"…are named everywhere and
defined nowhere"*, with a correction paragraph noting they are **not** added scope: they appear in
`BRD-Source.txt` line 6, in REQ-001, and `depot` is already a `partner_type` in
`Architecture.md:138`.

**Never created, though `Plan.md` §8 lists them as required practice artefacts:**
`RBAC.md`, `Glossary.md`, `Integrations.md`, `Security.md`, `Runbook.md`, `UAT.md`.

---

## 4. The delivery model (this is what makes 6.5 weeks arithmetically possible)

This is the single most important thing to preserve across the pivot, because it is not obvious
and it was contested once already.

**Contract-first, 10 layers, layers 3–9 ⛔ FROZEN** (`AGENTS.md` §3). The frozen layers are the
schema, the service signatures, the Zod contracts, the RLS policies, the API surface. Models
generate code *into* a fixed shape rather than inventing shapes.

**Test-gated delivery — code review was dropped entirely.** In its place:
- Acceptance criteria are written from the requirement **before** implementation.
- A **different model writes the tests** than writes the feature.
- **Mutation testing** proves the tests actually detect breakage.
- **Merge is blocked on green, not on approval.**

**Why this closes the arithmetic** (Plan.md §1, verbatim on the yes): *"**Yes — for all 62 P1
requirements plus most of what was previously the cut-line — conditional on four things.** That is
a real yes, not a hedged one."*

- 5 → 6.5 weeks = +30% calendar.
- Line-by-line human review "removes the single largest bottleneck. Review capacity was capping
  throughput at ~60k reviewed lines."
- Human review narrowed to ~**2–3k contract-layer lines** instead of ~130k.
- Testing moved onto the models.
- Net: **+2 days of new work offset by ~5 days removed.**

**Multi-model orchestration:** Opus 5, Sonnet 5, GPT 5.6 Sol. Nakul is architect and reviewer, not
typist.

**The reference-slice mechanism:** one hand-built vertical slice (**Leads**) in Week 1 becomes the
template that ~10 near-identical modules are cloned from. This is the actual load-bearing
assumption of the timeline.

**Generated RBAC test matrix:** ≈ 1,400 role × table × operation assertions, including negatives,
generated from `RBAC.md`. (Which is why `RBAC.md` not existing is a real problem, not a
documentation nicety.)

---

## 5. Architecture as committed

**Stack:** Next.js 15 App Router / React 19 / TypeScript strict · Expo SDK 54+ · Tailwind v4 +
shadcn/ui · TanStack Query + Table · react-hook-form + Zod · Framer Motion · next-intl.

**`src/server/services` is "the real contract."** Server Components and Server Actions call it
directly; REST exists only for mobile.

**`/api/v1` is a Week 1 Day 3 frozen deliverable** — frozen early specifically so the mobile track
can build against it without waiting. *This date turned out to matter enormously; see §8.*

**`activity_event`** — an append-only table every module writes to
(`entity_type`, `entity_id`, `customer_id`, `occurred_at`, `actor`, `payload`). It gives REQ-901's
360° customer timeline as a single indexed query and REQ-902 drop-off analysis nearly free. It is
also the **audit and attribution mechanism** — actor plus timestamp, append-only.

**Authorization:** Postgres RLS + a **hierarchy closure table** (ADR-004), with
`role_permission (role, module, action)`, action ∈ view / create / edit / approve / delete.

**Integrations behind interfaces with mock implementations**, e.g.
`src/server/integrations/whatsapp/provider.ts`.

**ERP: seams, not sync** (ADR-019) — `external_id`, `source_system`, `synced_at`, `sync_outbox`,
idempotency keys. ~1 day of work, vendor-neutral.

**Scale** (ADR-021): Supavisor transaction-mode pooling, no session state; every RLS policy column
indexed as a written discipline; nightly k6 at 300 concurrent; the `scale` seed profile promoted
into Week 1.

**Three-field sales-type model:** `sales_type` (renamed from `payment_type` — Commercial /
Subsidised / Project), `route_to_market`, `document_type`. One dropdown in the UI, the other two
derived. One stored column was not enough. *The rename was never executed.*

---

## 6. The register — requirements, decisions, issues, questions

### 6.1 Requirements — 73 total

Coverage summary at `Requirements.md:173`: **62 P1 · 11 P2 · 6 BLOCKED · 33 SPEC**
("SPEC" = the requirement exists but the business rule behind it is undefined).

Subsidy is **three rows** in the whole document:

```
| REQ-501 | Subsidy Management — track subsidy amount, approval status, disbursal
            separately from customer payment                          | P1 | SPEC | H | Q18 |
| REQ-502 | Farmer Payment Tracking — ledger of advance, subsidy portion,
            balance due, final settlement                             | P1 | SPEC | H | Q9, Q18 |
| REQ-503 | Audit-ready subsidy report: who is paid, what is pending,
            what is outstanding                                       | P1 | SPEC | M | Q18 |
```

Dealer portal is REQ-1101 … REQ-1112 (nine P1, two P2), including
`REQ-1105 | Stock Management — live stock across depots/warehouses, low-stock indicators`.

### 6.2 Decisions — ADR-001 … ADR-021

| ADR | Decision |
|---|---|
| 001 | Single Next.js app with route groups, not a monorepo |
| 002 | Supabase Postgres |
| 003 | Dual auth — email/password for staff, phone OTP for channel |
| 004 | RLS + hierarchy closure table |
| 005 | Server Components/Actions over a shared service layer; REST only for mobile |
| 006 | react-hook-form + Zod, TanStack Query, nuqs |
| 007 | shadcn/ui + Tailwind v4 + TanStack Table + Framer Motion |
| 008 | next-intl for en / hi / gu |
| 009 | WhatsApp Cloud API direct |
| 010 | Supabase Storage |
| 011 | pg_cron + Edge Functions |
| 012 | PDF via `@react-pdf/renderer` |
| 013 | Vitest + Playwright |
| 014 | Sentry from Week 1 |
| 015 | Vercel + Supabase Mumbai |
| 016 | **Tests are the delivery gate** |
| 017 | One Expo app, not two |
| 018 | Internal distribution, not public app stores |
| 019 | ERP seams, not a sync engine |
| 020 | WhatsApp behind a provider port (BSP-agnostic) |
| 021 | Transaction-mode pooling + RLS discipline for 100+ concurrent |

**Pending, never written** — the infrastructure move from Supabase + Vercel to
**Hostinger KVM 4 VPS (Mumbai) with Dokploy**:
- **ADR-022** VPS + Dokploy topology
- **ADR-023** Postgres + PgBouncer + `SET LOCAL` (RLS context under transaction pooling)
- **ADR-024** Better Auth (replacing Supabase Auth)
- **ADR-025** Object storage on-box → Cloudflare R2

These supersede ADR-002 / 003 / 010 / 015 and revise ADR-021. **ADR-026** (schema namespacing) was
drafted and is **moot** given the ERPNext/MariaDB direction. ⚠️ **The committed docs still say
Supabase + Vercel.** The infrastructure decision was made in discussion and never landed in the repo.

### 6.3 Issues — ISS-001 … ISS-026

| # | Title (abbreviated) |
|---|---|
| 001 | "Live stock" / "dispatch tracking" assume an unmentioned integration |
| 002 | Quotation vs tax invoice never distinguished |
| 003 | Employee location tracking is a compliance exposure |
| 004 | Background location impossible for web |
| 005 | BRD §5 RBAC table covers only 5 of 9 CRM roles |
| 006 | REQ-1112 describes three products in one line |
| 007 | Lead priority scoring has no owner |
| **008** | **Subsidy management is the least-specified section and is core to the business** |
| 009 | Ten reports with no periods, filters or targets |
| 010 | Hindi/Gujarati content is a client deliverable |
| 011 | Native app store-review risk |
| 012 | AI tests validating AI code share blind spots |
| 013 | Functional tests cannot catch schema or authz holes |
| 014 | Demo-scale seed hides performance problems |
| 015 | Planned ERP creates a two-master risk |
| 016 | Client's WhatsApp BSP is unnamed |
| 017 | Seasonal peaks make "100 concurrent" the wrong number |
| 018 | Connection exhaustion + per-row RLS cost invisible to functional tests |
| **019** | **Subsidy is eleven state workflows, not one Gujarat workflow** |
| **020** | **The fourteen subsidy stages are named but every sub-entry is "Detail Pending"** |
| 021 | Multi-state breaks the single-GSTIN tax assumption |
| **022** | **Depot and Institutional Sales are named everywhere and defined nowhere** (uncommitted edit) |
| 023 | Commission is money-critical and entirely unmapped |
| 024 | Two undeclared sales types and an undeclared role |
| 025 | Five of ten flowchart sheets are empty |
| **026** | **The dealer portal described is closer to a distributor ERP than a portal** — *now downgraded, see §7* |

### 6.4 Open questions — Q1 … Q53

Sections: **A** Commercial & scope · **B** External dependencies (lead times — start Day 1) ·
**C** Existing systems & data (architecture-determining) · **D** Business rules · **E** Product & UX ·
**F** Legal & compliance · **G** Testing, UAT & handover · **H** ERP, WhatsApp provider & scale
(added 2026-08-14) · **I** Raised by the client flowchart (added 2026-08-17) ·
plus a standing **assumptions** table A1–A8 and a **§Z kickoff shortlist**.

**§Z — the seven that must be answered before Day 1:**

1. **What runs stock, dispatch, invoicing and ledgers today?** (Q9 · ISS-001) — the dealer portal
   is a third of the scope and rests on this. Wrong answer = rebuild of order, stock and ledger
   modules plus 1–1.5 weeks of integration.
2. **Does the platform issue GST invoices, or only quotations?** (Q12 · ISS-002) — ask the client's
   **CA**, not only the client. E-invoicing/IRN is mandatory above the turnover threshold.
3. **Is the channel hierarchy a strict tree?** (Q13) — tree vs graph is schema-level. Discovering
   this in Week 3 means rebuilding authorization across ~25 tables. **Highest rework cost in the
   register (A4).**
4. **Permissions for Marketing, Accounts, Quality, Support, Admin** (Q32 · ISS-005) —
   **no assumption possible; this genuinely blocks Week 1.** The RBAC test matrix is *generated*
   from this, so an incomplete matrix means untested access paths.
5. **Field app — platform, devices, distribution** (Q29, Q30) — Google Play reviews
   background-location separately and routinely takes 2+ weeks with rejections. Internal
   distribution bypasses store review entirely.
6. **Subsidy** (Q18) — which schemes, tracking-only or portal integration, who updates status.
7. **System-of-record ownership sign-off** (Q39) — must be settled **before the Week 1 schema
   freeze**; it determines which tables get sync columns and which get write constraints.

**Standing assumptions we are proceeding on (A1–A8), with rework cost if wrong:**

| # | Assumption | Rework if wrong |
|---|---|---|
| A1 | CRM is source of truth in Phase 1; ERP gets *seams*, not a connector | Low |
| A2 | Quotations and orders only, **not** GST invoices with IRN | **High** — adds GSTN integration |
| A3 | Payments are **recorded**, not collected online | Medium — gateway + reconciliation |
| A4 | Channel hierarchy is a strict single-parent tree | **Very high** — authorization layer rebuild |
| A5 | Field tracking is check-in/check-out; background tracking is Phase 2 | Medium |
| A6 | Gujarat-only at launch; model still supports multi-state | Low |
| A7 | Subsidy is **tracked**; no government portal integration | Medium |
| A8 | English ships complete; Hindi/Gujarati keys wired, content follows | Low |

**Q43 is marked 🔴 BLOCKING.**

---

## 7. Decisions settled in meetings but not yet in the docs

These came out of the Loopify and Polysil conversations after the last commit. **None of them are
reflected in `Docs/` yet.**

**Dealer portal — settled at the BRD reading.** The portal shows **only the dealer's relationship
with Polysil**. In the worked example: Bharat bought 100 pipes from Polysil and sold 60 to farmers
— *the portal shows the 100, not the 60.* No personal sales, no own-godown stock, no dealer
invoicing. The BRD's "Live stock visibility across depots/warehouses" means **Polysil's stock shown
to the dealer**, not the dealer's own stock.

> This is the resolution of ISS-026 and it removes roughly **two weeks** of distributor-ERP risk.
> ISS-026 should be downgraded. This was the single largest scope reduction of the pre-pivot period.

Also settled: **no farmer login**, **no notifications** to farmers, **language dropped**,
**six states** (not eleven), **ERP deferred**, **replacement scoped to complained items only**.

---

## 8. The subsidy investigation — findings in full

This consumed the most analysis effort of any single topic, so it is recorded in full even though
the pivot may remove it.

### 8.1 What the domain actually is (verified, not asserted)

**Jantri = the government-approved MIS unit cost per hectare. Subsidy is computed on the Jantri,
not on the quotation.** Verified arithmetically against the client's own sheets:

| Check | Result |
|---|---|
| 181,684.51 × 0.55 | 99,926.48 ✓ |
| 181,684.51 × 0.45 | 81,758.03 ✓ |
| 145,059.04 × 0.80 | 116,047 ✓ |
| 145,059.04 × 0.70 | 101,541 ✓ |
| 145,059.04 × 0.85 | 123,300 ✓ |
| 145,059.04 × 0.90 | 130,553 ✓ |
| Farmer share: 202,830.39 − 99,926.48 + 10,292.72 GST | 113,196.63 ✓ |

**PMKSY / Per Drop More Crop:** Centre pays **55%** of indicative unit cost to small & marginal
farmers, **45%** to others. Centre:State 60:40. Max 5 hectares. DBT.

**GGRC (Gujarat Green Revolution Company) norms effective 24.04.2025** — these match the six
scheme rows in the client's screenshots exactly:

| Category | Rate |
|---|---|
| General ≥ 2 ha | 70% |
| Small & marginal < 2 ha, non-dark zone | 70% |
| Small & marginal < 2 ha, dark zone (57 talukas) | 80% |
| SC/ST | 85% |
| SC/ST dark zone | 90% |

**GGRC runs its own supplier portal** (`portal.ggrc.co.in` — MIS/OEM Supplier Registration;
farmer portal `khedut.ggrc.co.in`).

> **This is the key structural finding.** Flowchart stages 4–17 are **GGRC's stages, in GGRC's
> system**. Polysil's CRM **mirrors** them; it does not own or enforce them. Mirroring is cheap.
> This roughly halved my workflow-engine estimate.

### 8.2 What is actually hard

**One workbook contains at least three calculation bases:**
1. The 55/45 block (Jantri C1)
2. The 70/80/85/90 category block (Jantri C2)
3. "7 Year Cases Calculation 0.20 to 5 Ha Only"

**A second stacked scheme — ACF / Atal Bhujal:** `ACF % 5`, `PER Ha Limit 5000`,
`Max Amt. 10000`, `Ha Limit 2`, plus a **Village List** eligibility gate, plus "Parixit Share".
Four caps and a lookup table.

**Statutory document generation** (this was entirely omitted from my first estimate): Techno Report
Crop1/Crop2, PVC & GI Fitting List, Solvant Cal Sheet, Exi Letter, and the Gujarati annexures
**પાણી પત્રક** (water sheet), **પાણીની સમિતિ અને પાણી પત્રક** (water committee),
**ભાગીદારીની સંમતિ** (partnership consent).

**Three GST rates in one document:** 5% on MIS (2.5 + 2.5), 18% on insurance and MIS inspection
charge (9 + 9), 0% on Farmer Education & Training.

**Cost build:** A Head Unit Cost · B Field Unit Cost · C Installation Charges ·
D Insurance @ 0.28% of (A+B+C+GST) · E MIS Inspection Charge @ 0.4% of (A+B) ·
F Farmer Education & Training ₹1,000 · G No Sump → "COST of MIS (A+B+C+D+E+F)".

**Undocumented business rules visible in the sheets:** `No Sump`, `Discount % 10`,
`(Chillies)+(Select Crop here)`, `(1.37 x 0.50)` lateral/dripper spacing, and notes about excess
PVC/HDPE pipe length and double laterals "resulting in increased MIS cost".

**"MIS System" = the system type** (Drip / Mini Sprinkler / Sprinkler / others) — this is the key
that selects the subsidy template. State × system type is the template matrix.

**Rates are effective-dated and change.** A submitted government file must stay priced at the norms
it went in under. This is a versioning requirement, not a config value.

### 8.3 The three-tier estimate, against a BRD that budgeted 2–3 days

| Tier | Scope | Estimate |
|---|---|---|
| **1 — Track** | Mirror GGRC stages, record amounts and status, audit report | 20–24 d ≈ 4–5 wk |
| **2 — Track + compute** | Above, plus the farmer-share calculation engine | 32–39 d ≈ 6.5–8 wk |
| **3 — Replace the Excel** | Above, plus statutory document generation, ACF stacking, state × system templates | **50–69 d ≈ 10–14 wk** |

> **The single unasked question that swings this by five-plus weeks:**
> *does the CRM replace that workbook, or point at it?*

I said plainly that my earlier "7.5–9.5 weeks" figure was **right by accident** — I had over-priced
the workflow engine and under-priced the calculation layer, and the real error was giving one
number for a scope with a five-week fork inside it.

### 8.4 The decision Loopify took

Timeline cannot move much (maybe a week). Price could increase but there is no point. **Loopify
wants Tier 3 — replacing the Excel completely.**

**Nakul's proposal, accepted and communicated to Loopify:** Loopify assigns a team member solely to
Subsidy. **Nakul does not touch subsidy** and builds everything else.

The reasoning, in Nakul's words: *"its not just subsidy can be done, understanding that with other
things, is a complete different task and mindset, so no point going for that, for some money,
already project is way bigger."*

**My assessment: the decision is correct.** Not primarily for capacity reasons — for cognitive
ones. Subsidy is a different domain (government compliance, effective-dated statutory rates,
Gujarati document generation) running on a different clock (GGRC's, not Polysil's). Splitting it
off is cleaner than time-slicing one person across two mental models.

### 8.5 The proposed integration shape (designed, never executed)

**Subsidy becomes App 4 — a second consumer of the already-frozen `/api/v1`.** Exactly the pattern
App 3 (mobile) already uses. Separate repo, separate Postgres database, separate Dokploy app.
It reads CRM data **through `/api/v1`, never through SQL.**

This is a deliberate departure from ADR-001 and requires **ADR-027**, recording that the departure
is justified on **contractual** grounds (blame attribution across two parties) rather than
technical ones.

**Blame attribution rests on mechanisms that already exist:**
- `activity_event` — actor plus timestamp, append-only
- Test-gated acceptance suites, one per REQ-ID
- Contract-layer human review
- One REQ-ID per branch and per PR

**Two mechanisms to add so neither party blocks the other:**
1. **A stub of the subsidy service, owned by Nakul**, built the same day the API freezes — so
   Nakul's tracks compile and test without the other developer's code existing.
2. **A frozen seed dataset**, handed over on day one — so the subsidy developer is never blocked
   waiting for Polysil's master data, and neither party can claim the other stalled them.

### 8.6 ⚠️ The deadline nobody had noticed

**`/api/v1` freezes on Week 1 Day 3.**

If it freezes without the subsidy service's endpoints in it, it has to be unfrozen in Week 3 —
**which also breaks the mobile track**, because App 3 builds against that frozen contract.

> **Therefore the one-time handoff discussion with the subsidy developer has a hard date:
> before Week 1 Day 3.** Not "early in the project." Before day three.

---

## 9. The 6.5-week plan as written

### 9.1 The four conditions the "yes" depends on

1. **Seven kickoff questions answered before Day 1** — especially permissions for the five
   undefined roles.
2. **Q9 RESOLVED** (ERP is planned, not live; seams ≈ 1 day). Residual is
   **Q39 — the system-of-record ownership table, before the Week 1 schema freeze.**
3. **Week 0 dependencies start immediately** — BSP API access + inbound webhooks (Q36), TRAI DLT
   registration, app distribution. These have 3–15 working day external lead times.
4. **Field app Android-first, internal distribution.**
5. **Scale designed in, not tuned later.**

**Designated cut-line if something must give:** REQ-1204, REQ-1209, REQ-1102, REQ-903.

### 9.2 Week by week

| Week | Content |
|---|---|
| **W1** | Contracts & the Leads reference slice. **D1** glossary / ERD / `RBAC.md`. **D2** schema + RLS + audit trigger + closure table + sync seams. **D3** `src/contracts/**` Zod, service signatures, **`/api/v1` contract frozen for mobile**, auth. **D4** design system / shadcn / app shell / i18n scaffolding. **D5** CI gates, RBAC test matrix, seed profiles, Leads slice. |
| **W2** | Sales Core. |
| **W3** | Quote-to-Order & Channel. **Mobile track opens.** |
| **W4** | Service, Money & Communication — **includes REQ-501/502/503 (subsidy + farmer payment ledger)** alongside REQ-801..806, REQ-1106, REQ-601..605, and mobile REQ-701/702. |
| **W5** | Insight & the rest. |
| **W6** | Hardening, D26–D30. |
| **W6.5** | UAT & cutover, D31–D33. |

> Note: subsidy at **Tier 0** was always scheduled — Week 4, three requirements. The plan was never
> wrong about subsidy. **Tier 3 simply was never in it.**

### 9.3 Cadence

- 09:30 daily contract
- One REQ-ID per branch and per PR
- **Merge blocked on green, not on approval**
- 17:00 merge window
- Nightly on `main`: Playwright, mutation, performance, visual regression.
  *"A red nightly stops new feature merges until green."*
- Friday 15:00 client demo · 17:00 retro
- Risk register **R1–R13** reviewed every Friday; a question 🔴 for two consecutive weeks is
  escalated in writing

---

## 10. What actually threatens the date (pre-pivot assessment)

Not subsidy — subsidy was handed off. These:

1. **The seven kickoff questions** (§6.4 §Z) — several are schema-level and cannot be assumed.
2. **R5 — five undefined CRM roles** (Marketing, Accounts, Quality, Support, Admin). The RBAC test
   matrix is *generated* from `RBAC.md`, and `RBAC.md` does not exist.
3. **Q39 — system-of-record ownership, before the schema freeze.**
4. **Five blank flowchart sheets** — Daily Work Planner & Task Management, Scheme Management,
   Reports, Dashboard, and **the entire Mobile App**. App 3 has no specification at all.
5. **The infrastructure ADRs (022–025) never written**, so the committed docs describe a stack
   (Supabase + Vercel) we had already decided to leave.
6. **The `sales_type` rename never executed.**

---

## 11. Source documents — key quotations

**`BRD-Source.txt` §2.5, Subsidy — this is the entire subsidy specification in the signed BRD:**
> "the system tracks the **subsidy amount, approval status and disbursal** separately from the
> customer's own payment" + "Full payment ledger per farmer/consumer covering advance, subsidy
> portion, balance due and final settlement."

Two sentences. Against which §8 sets out a 10–14 week Tier 3 scope.

**`BRD-Source.txt`, dealer portal:** "A dedicated portal for Dealers, Sub Dealers and Agents."
Stock Management = "Live stock visibility across **depots/warehouses**, with low-stock indicators."

Other landmarks: line 6 channel chain · line 20 3-Way Sales Tracking · line 58
English/Hindi/Gujarati · lines 85–120 role table with **exactly 5 rows, Distributor absent**.

**`Flowchart-Source.md`** — verbatim extract of `CRM and DMS Flowchart.xlsx`, 10 sheets, 5 empty.

- **Sheet 2** — lead fields, stages 4–17, 11 states, "State Wise Separate Stages Required",
  "Add Stage Option require", "Sub Entries Level Pending",
  "Subsidied — Quotation Templets and Calculation Pending"
- **Sheet 3** — five sales types including **Export** and **Replacement Order**; approval chain
  Managers → Account → State Head
- **Sheet 4** — complaint → Manager approval → Quality Checking → Replacement Order
- **Sheet 5** — DMS list including Sub-dealer Add, Inventory Add, Invoices of Dealer, Reward Points
  Redeem, and two Won-lead Commission reports
- **Empty sheets** — Daily Work Planner & Task Management · Scheme Management · Reports ·
  Dashboard · **Mobile App (App 3 in its entirety)**

---

## 12. Work that was designed but never executed

Everything here was proposed, agreed in principle, and never written to the repo. It is listed so
the pivot can explicitly kill or keep each item rather than losing it silently.

**Plan.md edits**
- Remove REQ-501/502/503 from Week 4 (they transfer with the subsidy module)
- Add subsidy endpoints to the Week 1 D3 `/api/v1` freeze
- Add subsidy case linkage + payment-ledger portion to the Week 1 D2 schema

**New decision and risk records**
- **ADR-027** — external module boundary; departure from ADR-001 on contractual grounds
- **R14** — second-party delivery risk
- **ADR-022 … ADR-025** — the VPS/Dokploy infrastructure move (ADR-026 is moot)

**Issue reclassification**
- ISS-008, ISS-019, ISS-020 transfer with the subsidy module
- ISS-026 downgraded (dealer portal settled at the BRD reading)

**Documents**
- The `/api/v1` subsidy contract, as OpenAPI
- The scope-split email to Loopify
- `Docs/Meeting-Brief.md`
- `Docs/RBAC.md`, `Glossary.md`, `Integrations.md`, `Security.md`, `Runbook.md`, `UAT.md`

**Open-Questions.md maintenance**
- Close resolved questions with "confirmed by Polysil, [date]"
- Add Q54 / Q55 / Q56

**Requirements.md**
- Add the subsidy state × system-type template model
- New REQ blocks before the Week 1 schema freeze: commission · quotation engine detail · approvals
  inventory (7 chains) · dealer inventory/invoicing · sub-dealer add · reward redemption ·
  Export / Replacement · State Head · Survey & Design · subsidy workflow engine

**Schema**
- The `sales_type` rename (from `payment_type`)

---

## 13. Corrections made during this period — recorded so they are not repeated

1. **I estimated remaining scope from scratch (84–106 days ≈ 17–21 weeks) without reading the
   repo.** Corrected: *"you already have everything planned, and mentioned in repo, easily
   completable under 6.5 weeks."* The number was retracted. **The lesson: the delivery model is
   multi-model orchestration with Nakul as architect/reviewer, not hand-written solo work.
   Estimates built on solo-typing assumptions are wrong by roughly 2×.**
2. **I over-priced the subsidy workflow engine and under-priced its calculation layer.** GGRC owns
   the authoritative stage state on its own portal, so the CRM only mirrors. But I gave
   farmer-share calculation 5–7 days having never seen the sheets, and omitted statutory document
   generation entirely.
3. **I recommended a separate repo/DB/deploy for subsidy without acknowledging ADR-001.** Corrected
   by framing it as a deliberate, documented departure (ADR-027) and reframing subsidy as **App 4
   following the existing App 3 pattern** — so the boundary is not new work.
4. **ISS-022 originally claimed Depot and Institutional Sales were missing from the hierarchy.**
   They are not. They are in the BRD, in REQ-001, and in `Architecture.md:138`. They are
   *undefined*, not *absent* — and must not be raised with the client as added scope.

---

*End of snapshot. Everything above describes the project as of 2026-09-06, before the pivot.*
