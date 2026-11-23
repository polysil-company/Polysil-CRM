# Issues

Problems found — in the BRD, in the plan, or in the build. Distinct from [Open-Questions.md](Docs/Open-Questions.md): a *question* is something we don't know. An **issue** is something we know is wrong, ambiguous, contradictory, or risky, and that someone must act on.

| Status | Meaning |
|---|---|
| 🔴 OPEN | Identified, not addressed |
| 🟡 MITIGATED | A workaround or plan is in place; the underlying problem remains |
| 🟢 RESOLVED | Fixed or formally decided; keep the row for history |

| Severity | Meaning |
|---|---|
| **S1** | Legal, financial or security exposure — or breaks the delivery date |
| **S2** | Causes rework, or a client dispute, if not addressed |
| **S3** | Quality or clarity problem; fix before go-live |

---

## A. Issues found in the BRD

### ISS-001 · "Live stock" and "dispatch tracking" assume an integration that is never mentioned
**Severity:** S1 · **Status:** 🔴 OPEN · **Refs:** REQ-1101, REQ-1103, REQ-1105, [Q9](Docs/Open-Questions.md)

Section 3 promises dealers "live pricing and stock availability", "live stock visibility across depots/warehouses" and dispatch status "from order confirmation through to delivery". None of that data originates in a CRM — it lives in whatever runs the warehouse and invoicing today (Tally, SAP, Busy, or spreadsheets). The BRD never names that system or specifies a sync.

**Impact.** The dealer portal is roughly a third of the scope and rests entirely on this answer. Two-way ERP sync is 1–1.5 weeks of work that is currently in nobody's plan.

**Action.** Force the answer in Week 0. Until then we proceed on assumption A1 (CRM is source of truth, stock entered manually), and that assumption is stated to the client in writing rather than buried.

---

### ISS-002 · Quotation vs. tax invoice is never distinguished
**Severity:** S1 · **Status:** 🔴 OPEN · **Refs:** REQ-203, [Q12](Docs/Open-Questions.md)

The BRD says "product-wise, GST-calculated quotation". A quotation is a commercial document with no statutory obligations. A **tax invoice** has mandatory fields, an unbroken serial series, and — above the turnover threshold — e-invoicing with an IRN from the government IRP plus e-way bills for goods movement. For a company of this size, the threshold is almost certainly crossed.

**Impact.** If the client expects the platform to *invoice*, that is a GSTN integration and roughly a week of work not in the plan, plus real legal exposure if done wrong.

**Action.** Confirm with the client's CA, not just the client. Currently assumed out of scope (A2).

---

### ISS-003 · Employee location tracking is specified as a feature, but is a compliance exposure
**Severity:** S1 · **Status:** 🟡 MITIGATED · **Refs:** REQ-702, REQ-705, [Q25](Docs/Open-Questions.md)

"Live location tracking and route history" for field staff means continuously storing an identified employee's physical movements. Under the **DPDP Act 2023** that is personal data requiring a lawful basis, notice, and consent — and it needs to sit inside an employment policy. The BRD treats it purely as a monitoring feature.

**Impact.** Sharpest legal risk in the document, and it is the kind that surfaces during an employment dispute rather than during UAT.

**Mitigation.** REQ-705 added (consent + privacy notice). Tracking limited to working hours by design. Client's HR/legal must supply the policy basis before go-live.

---

### ISS-004 · Background location tracking is technically impossible as scoped for web
**Severity:** S2 · **Status:** 🟡 MITIGATED · **Refs:** REQ-702, [Q21](Docs/Open-Questions.md)

Continuous tracking requires an OS-level background service. iOS Safari has **no** background geolocation for web apps — not a permission, the capability doesn't exist. Android throttles it aggressively.

**Mitigation.** Resolved by the client's confirmation that Field Sales is a **native mobile app**, not a PWA. See ISS-011 for the new risk this introduces.

---

### ISS-005 · The RBAC table in BRD §5 is incomplete, and covers only 5 of 9 stated CRM roles
**Severity:** S1 · **Status:** 🔴 OPEN · **Refs:** REQ-1301, [Q32](Docs/Open-Questions.md)

Two separate defects:

1. The table's final row (Dealer / Sub Dealer / Agent) stops after "No approval rights" — the **Delete** column is never filled.
2. The client has since named nine CRM user types (Management, Regional/Area Manager, Sales Manager, Sales Executive, **Marketing, Accounts, Quality, Support, Admin**). The BRD's matrix defines only the first four plus the portal role. **Marketing, Accounts, Quality, Support and Admin have no defined permissions at all.**

This directly contradicts the BRD's own stated principle: *"no module is left with undefined or default access."*

**Impact.** Five undefined roles is five sets of RLS policies that cannot be written. Blocks REQ-1301 and, transitively, every module's authorization.

**Action.** Produce the full role × module × action matrix in `Docs/RBAC.md` and get it signed. This is the highest-value single artefact still missing.

---

### ISS-006 · REQ-1112 (Customer Relationship Portal) describes three different products in one line
**Severity:** S2 · **Status:** 🔴 OPEN · **Refs:** REQ-1112, [Q24](Docs/Open-Questions.md)

*"Direct mobile-number based lead and company detail capture for end consumers, with marketing/branding content and rating."* That reads as (a) a lead-capture form, (b) a marketing microsite, and (c) a customer self-service area — three different builds with three different scopes.

Compounding it: the client has now placed Customer/Farmer inside **Web Application 2 alongside dealers**. A farmer and a distributor have almost nothing in common in navigation, vocabulary, or data. Sharing a codebase is fine; sharing an interface is not.

**Action.** Define what a farmer actually *does* there in one paragraph. Until then, scoped as: OTP login → my orders → my warranty → raise complaint → rate service.

---

### ISS-007 · Lead priority scoring has no owner, and unowned scoring gets ignored
**Severity:** S2 · **Status:** 🔴 OPEN · **Refs:** REQ-106, [Q14](Docs/Open-Questions.md)

The BRD specifies automatic Hot/Warm/Cold scoring from "source quality, enquiry value, response time and engagement level" without weights or thresholds. We can propose a model, but this is a product problem before it is an algorithm problem: if the client's sales head does not *own* the model, the team stops trusting the badges within a fortnight and the feature becomes decoration.

**Action.** Sales head defines v1 weights. Build the scorer configurable (weights in a table, not in code) so it can be tuned post-launch without a deploy.

---

### ISS-008 · Subsidy management is the least-specified section, and it is core to the business
**Severity:** S1 · **Status:** 🔴 OPEN · **Refs:** REQ-501, REQ-502, REQ-503, [Q18](Docs/Open-Questions.md)

Section 2.5 is three sentences for what is, for a micro-irrigation company in Gujarat, a central workflow. Unanswered: which schemes (PMKSY, state/iKhedut), whether we integrate with a government portal or only track, who updates approval status and from what evidence, what the disbursal stages are, and how a partially-disbursed subsidy interacts with the farmer's balance.

**Impact.** "Audit-ready record" (the BRD's own words) is not achievable against an undefined workflow. High rework risk if built on a guess.

---

### ISS-009 · Ten reports are specified with no definition of the periods, filters, or targets behind them
**Severity:** S2 · **Status:** 🔴 OPEN · **Refs:** REQ-1201..1210, [Q27](Docs/Open-Questions.md)

"Target vs Achievement" has no target-setting mechanism anywhere in the BRD — no table, no screen, no owner. "Sales Forecast" needs a stated methodology. Every report needs its period granularity (daily/weekly/monthly/quarterly/FY), its filter set, and its drill-down behaviour defined, or ten reports become thirty rounds of revision.

**Action.** One-page spec per report before Week 5. Target-setting becomes its own requirement once Q27 is answered.

---

### ISS-010 · Hindi and Gujarati are listed as a feature, but the content is a client deliverable
**Severity:** S3 · **Status:** 🟡 MITIGATED · **Refs:** REQ-1002, [Q22](Docs/Open-Questions.md)

We can wire three locales in Week 1. We cannot write professional Gujarati B2B copy, and machine translation reads badly to native speakers — on a dealer-facing product that is a credibility problem, not a polish problem.

**Mitigation.** Keys wired from Day 1 (retrofitting i18n across 60 screens in the final week is a guaranteed failure). Translation content is a named client deliverable with a Week 4 due date. English ships complete regardless.

---

## B. Issues arising from scope and delivery

### ISS-011 · Native mobile app introduces store-review risk that can exceed the project window
**Severity:** S1 · **Status:** 🔴 OPEN · **Refs:** REQ-701, REQ-702, [Q30](Docs/Open-Questions.md)

Now that Field Sales is a native app, background location becomes possible — but **Google Play reviews background-location permission separately**, requires a justification video, and routinely takes 2+ weeks with rejections. Apple scrutinises `always` location similarly. A public store listing could easily outlast the entire build.

**Mitigation (recommended).** Field staff are employees, not the public. Distribute internally — signed APK, Play Internal App Sharing, or Managed Google Play — which bypasses public store review and background-location review entirely. Only if iPhones are in use does this need TestFlight or Apple Business Manager.

**Action.** Confirm device fleet (Q29) and distribution channel (Q30) in Week 0. This is now the longest external lead time in the project.

---

### ISS-012 · AI-written tests validating AI-written code share the same blind spot
**Severity:** S1 · **Status:** 🟡 MITIGATED · **Refs:** [Testing.md](Docs/Testing.md)

With code review deliberately dropped in favour of automated testing, tests become the *only* correctness gate. But if the same model writes the implementation and its tests, a misunderstood requirement produces a wrong implementation and a test that confirms the wrong behaviour. The suite goes green and nothing is actually verified.

**Mitigation (three layers).**
1. **Acceptance criteria are written from the requirement, before implementation** — the test spec derives from `Docs/`, never from the code.
2. **A different model writes the tests than writes the feature.** Adversarial pairing, enforced by the routing table in [AGENTS.md](Docs/AGENTS.md).
3. **Mutation testing** on the business-logic core (GST, scoring, ledger, SLA, hierarchy) to prove the tests actually detect broken behaviour rather than merely executing it.

---

### ISS-013 · Functional tests cannot catch schema mistakes or authorization holes
**Severity:** S1 · **Status:** 🟡 MITIGATED

Two failure classes are invisible to functional testing:

- **Authorization holes** — the happy path works perfectly, so every functional test passes, while a role can read rows it shouldn't. A test only catches what someone thought to test.
- **Data-model mistakes** — a wrong cardinality (one-to-many where it should be many-to-many) passes every test and surfaces in month three as a rebuild.

**Mitigation.** (a) The RLS test matrix is **generated** from `Docs/RBAC.md` — every role × table × operation asserted, including the negative cases, so coverage is mechanical rather than imagined. (b) The frozen contract layer (schema, Zod, service signatures) is the *one* thing still human-reviewed — roughly 2–3k lines, not 130k. Review effort is spent where tests structurally cannot reach.

---

### ISS-014 · Seed data at demo scale hides performance problems until production
**Severity:** S2 · **Status:** 🔴 OPEN

Tests against 50 seeded rows pass instantly. The same report against 500k activity events and 3,000 dealers times out. The 360° timeline (REQ-901) and the ten reports are the likely casualties.

**Action.** Two seed profiles: `demo` (realistic Gujarat data for client demos) and `scale` (500k+ rows for performance assertions in CI). Report queries get an explicit budget — p95 under 2s at scale — asserted in CI, not checked by hand.

---

### ISS-015 - Planned ERP creates a two-master risk that must be settled before schema freeze
**Severity:** S1 - **Status:** MITIGATED by [ADR-019](Docs/Decisions.md), ownership table pending sign-off

The client is planning an ERP and wants it synced with the CRM. The ERP does not exist yet, so there is nothing to integrate with - but there is something to get wrong. If the CRM is built as the owner of products, pricing, stock and invoices, and the ERP later claims those same entities, the result is two systems each believing they are authoritative. That disagreement surfaces as wrong prices on quotations and stock that does not reconcile, typically after enough data exists that neither side can simply be overwritten.

Retrofitting is the expensive part: adding identity-mapping columns and change capture to a live system with 500k+ rows is a migration project with real data risk. Doing it on empty tables costs about a day.

**Action.** System-of-record ownership table written and signed off before the Week 1 schema freeze ([Architecture.md section 10](Docs/Architecture.md), [Q39](Docs/Open-Questions.md)). Sync seams built in Week 1: identity columns, `sync_outbox`, idempotency keys, all writes through services. No connector built.

---

### ISS-016 - The client's WhatsApp BSP is unnamed, and BSP APIs are not interchangeable
**Severity:** S2 - **Status:** MITIGATED by [ADR-020](Docs/Decisions.md)

Using the client's existing provider removes Meta Business verification from the critical path, which is a real gain. It also replaces a documented API with an unknown one. Indian BSPs differ in every dimension that matters to us: template management, webhook payload shape, media handling, delivery receipts, and whether inbound messaging is available at all on the client's plan. REQ-601 (two-way conversation within the 24-hour session window) is the requirement most likely to be blocked, because some BSPs simply do not expose inbound webhooks below a given tier.

**Action.** Provider port with a mock implementation, so all five WhatsApp requirements are built and tested in Week 2 without credentials. Confirm inbound webhook availability before Week 2 begins ([Q36](Docs/Open-Questions.md)). Template texts remain a Week 0 deliverable - approval is Meta's, not the BSP's.

---

### ISS-017 - Seasonal peaks make "100 concurrent" the wrong number to size against
**Severity:** S2 - **Status:** MITIGATED by [ADR-021](Docs/Decisions.md)

Irrigation demand in Gujarat is strongly seasonal, and subsidy applications cluster around deadlines. A system sized for 100 concurrent users will meet its real test in a two-hour window when every field executive and a large share of dealers are on it simultaneously - which is exactly when being down is most damaging commercially.

**Action.** Design and load-test to **300 concurrent**, not 100. Load test at that level is a nightly CI gate against the `scale` seed.

---

### ISS-018 - Connection exhaustion and per-row RLS cost are invisible to functional tests
**Severity:** S1 - **Status:** MITIGATED by [ADR-021](Docs/Decisions.md) + load-test gate

This is the scale-specific instance of [ISS-013](Docs/Issues.md). Every functional test passes with one user and fifty rows. Two failures appear only under concurrency: Postgres connections exhausted by serverless fan-out, and RLS policies whose per-row subquery cost is unnoticeable at 50 rows and fatal at 500k. Both produce a system that works perfectly in every test and in every demo, and falls over on the first busy morning.

**Action.** Transaction-mode pooling enforced in the frozen contract layer. RLS discipline enforced in policy review, which is one of the few things still human-reviewed ([Testing.md section 1](Docs/Testing.md)). Load test at 300 concurrent plus report p95 assertions at `scale` seed, both nightly CI gates.

---

### ISS-019 - Subsidy is eleven state workflows, not one Gujarat workflow
**Severity:** S1 - **Status:** OPEN, blocks scope and estimate

The flowchart lists subsidy states GJ, UP, MH, KA, TN, Andhra, TG, RJ, CG, MP, HR, with named owners against four of them, and states plainly: **"State Wise Separate Stages Required"**. Everything scoped so far assumed a Gujarat-centric single subsidy pipeline. Eleven state pipelines is a different system: different departments, different portals, different stage names, different document sets, different farmer-share formulas.

**Action.** Build subsidy as a **configurable workflow engine** - stages as data rows in a `subsidy_workflow_stage` table keyed by state, not as a Postgres enum or a hardcoded constant. The client explicitly asks for "Add Stage Option require", which confirms it. Configuring one state then costs hours; hardcoding one state and discovering ten more costs a rewrite. Configure **only the states confirmed in [Q43](Docs/Open-Questions.md)** for go-live.

---

### ISS-020 - The fourteen subsidy stages are named, but every sub-entry is "Detail Pending"
**Severity:** S1 - **Status:** OPEN

Stages 4-17 are now known (Application Process through FP Received from Department). But row 39 of the sheet reads **"Sub Entries Level Pending and Requiremennt pendinng from our side"** and is marked *Detail Pending* against every single state column. Stage names alone are not buildable: each stage needs its fields, its required documents, its allowed transitions, who can move it, and what an "In Query" resolution looks like.

**Action.** The workflow engine from [ISS-019](Docs/Issues.md) lets us build the machinery without the details. But at least **one state must be fully detailed before Week 3** or there is nothing to validate the engine against ([Q46](Docs/Open-Questions.md)). This is now the top-ranked specification dependency.

---

### ISS-021 - Multi-state operation breaks the single-GSTIN tax assumption
**Severity:** S1 - **Status:** OPEN

[AC-203](Docs/Acceptance-Criteria.md) was written assuming a Gujarat-registered seller, where CGST+SGST is the common case and IGST the exception. Across eleven states that inverts. Worse, if Polysil holds GST registrations in more than one state - which the **Depot** tier in the channel chain strongly suggests - then the CGST/SGST-versus-IGST determination depends on the *supplying* GSTIN state, not the head office. Place of supply also has its own rules that are not simply "the buyer state".

**Action.** Cannot be resolved by us. [Q45](Docs/Open-Questions.md) to the client CA: how many GSTINs, in which states, and which one supplies which customer. Until answered, quotations carry an explicit place-of-supply field and the tax engine takes *both* GSTINs as input rather than assuming one.

---

### ISS-022 - Depot and Institutional Sales are named everywhere and defined nowhere
**Severity:** S2 - **Status:** OPEN

**Correction to the first version of this issue.** Depot and Institutional Sales are *not* new - they appear in [BRD-Source.txt line 6](Docs/BRD-Source.txt) and in [REQ-001](Docs/Requirements.md), and `depot` is already a `partner_type` in the [Architecture.md line 138](Docs/Architecture.md) sketch. The flowchart repeats the same chain. So this is not added scope and must not be raised as such.

The actual problem is that all three sources name these tiers and none of them defines what they are. *Depot* is most likely a company-owned stocking point rather than a trading partner - which would make it an inventory location with a possible separate GSTIN, not a hierarchy node at all. *Institutional Sales* and *Employees* read like parallel sale channels, not tiers in a chain. REQ-001 has been `SPEC` status against [Q13](Docs/Open-Questions.md) since day one for exactly this reason.

**Action.** The closure table absorbs extra tiers without a schema change, so this is cheap *if* settled before freeze. What it changes is RBAC scope resolution and every territory report. [Q50](Docs/Open-Questions.md).

---

### ISS-023 - Commission is money-critical and entirely unmapped
**Severity:** S1 - **Status:** OPEN

The DMS sheet asks for **"Won lead Commission Amt Report"** and **"Won lead Other Commission Report"**. Commission does not appear anywhere in [Requirements.md](Docs/Requirements.md), in the BRD, or in the plan. It is a payout calculation - the class of feature where a rounding error becomes a partner dispute and a silent slab error becomes a recurring overpayment nobody notices for months.

**Action.** Treat as new scope, not as a report. It needs its own requirement block, its own acceptance criteria, property-based tests, and Opus 5 ownership under the same money-critical rules as GST. [Q48](Docs/Open-Questions.md) defines the rules. Until that is answered it is **not estimable**.

---

### ISS-024 - Two undeclared sales types and an undeclared role
**Severity:** S2 - **Status:** OPEN

The Sales Order sheet adds **Export** (manual rates - so foreign currency? LUT or zero-rated supply? shipping documents?) and **Replacement Order** (complaint-only, presumably zero-value). It also introduces a **State Head** as the third and final approver, a role absent from the nine CRM roles scoped in [Requirements.md](Docs/Requirements.md).

Export is not a variant of a domestic order. Zero-rated supply under LUT, or IGST-paid-with-refund, is a distinct tax treatment with distinct documents.

**Action.** [Q49](Docs/Open-Questions.md) for State Head placement in the hierarchy. Recommend that **Export is explicitly deferred out of Phase 1** unless the client shows meaningful volume - it carries disproportionate compliance weight for what is likely a handful of orders.

---

### ISS-025 - Five of ten sheets are empty, and they are the five we already could not specify
**Severity:** S1 - **Status:** OPEN

`Daily Work Planner & Task Management`, `Scheme Management`, `Reports`, `Dashboard` and `Mobile App` contain nothing at all. These map to REQ-201..206, REQ-301..305, REQ-701..705, REQ-1001..1002 and REQ-1201..1211 - already the largest cluster of `SPEC` items in the register. The entire mobile application, one of the three deliverables, has a blank sheet.

**Action.** This file **confirms** the specification gap rather than closing it. [ISS-002](Docs/Issues.md) stands unchanged, and its severity is now evidenced rather than inferred. The Week 0 requirements workshop is not optional.

---

### ISS-026 - The dealer portal described here is closer to a distributor ERP than a portal
**Severity:** S2 - **Status:** OPEN

The DMS sheet asks for dealer-side **Inventory Add**, **Invoices of Dealer**, **Accounting & Payment**, and **Material Planning (stock management / advance planning)**. That is a dealer stock ledger and dealer invoicing - a distribution management system in the literal sense, not a company portal onto company data. It also sits directly on top of the ERP boundary drawn in [Architecture.md section 10](Docs/Architecture.md).

**Action.** [Q51](Docs/Open-Questions.md). The likely correct Phase 1 line is that dealers *record* stock movements and *upload* invoices as documents, and do not get a valued inventory and invoicing engine. That distinction is worth roughly two weeks and must be agreed in writing.

---

## C. Resolved

*(none yet)*
