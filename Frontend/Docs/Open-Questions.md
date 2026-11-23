# Open Questions

Every ambiguity in this project lives here with a **named owner** and a **due date**. An open question without an owner never gets answered.

**Rule:** a requirement marked `SPEC` in [Requirements.md](Docs/Requirements.md) does not enter a sprint until its question here is answered and an ADR or Docs entry records the answer.

> **Going into the kickoff call?** Jump to [§Z — Ask before project start](#z-ask-before-project-start) at the bottom. It is the short list that changes the plan most.

| Status | Meaning |
|---|---|
| 🔴 OPEN | No answer. Blocking. |
| 🟡 ASSUMED | We have proceeded on a stated assumption. **If wrong, rework follows.** |
| 🟢 ANSWERED | Recorded in Docs. Requirement moves to `READY`. |

---

## A. Commercial & scope — answer before Week 1 ends

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q1 | Is Day 35 a **contractual go-live** or an internal target? What exactly must be true on that date — production live with real users, or UAT-ready on staging? | Determines whether Week 5 is a launch week or a buffer week. Changes the whole plan. | Loopify ↔ Client | 🔴 |
| Q2 | Is there a **signed Phase 1 / Phase 2 split**? Does the client currently believe all 73 requirements land in 5 weeks? | 73 requirements is a 5–7 month conventional build. If expectations are unaligned, that surfaces in Week 4 as a dispute rather than in Week 0 as a plan. | Loopify | 🔴 |
| Q3 | Who is the **single client-side decision maker**, and can they give 20 minutes daily? | 33 undefined rules cannot be resolved through a committee at this pace. | Client | 🔴 |
| Q26 | Who owns the **IP and the repository**? Where does production infrastructure live — our accounts or the client's? | Affects handover, billing, and what we can build on later. | Loopify ↔ Client | 🔴 |

## B. External dependencies — these have lead times; start Day 1

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q4 | **WhatsApp:** Is the Meta Business Manager verified? Is there a dedicated phone number *not* currently on consumer WhatsApp? Who pays Meta conversation charges? | Verification runs 3–15 working days, template approval 1–3 days each. REQ-601..604 (5 requirements) cannot go live without it. | Client | 🔴 |
| Q5 | **Meta Lead Ads / Google Ads:** who owns the Page, Ad Account and Google Ads account? Are we permitted to submit a Meta App Review for `leadgen_retrieval`? | REQ-102/104. App Review alone can exceed the project window — this is why both are P2. | Client | 🔴 |
| Q6 | **SMS:** Is TRAI **DLT registration** complete? Is there a registered sender ID and template set? | Without DLT, no OTP and no SMS reminders in India. Blocks REQ-000 and REQ-303 in production. 5–15 working days. | Client | 🔴 |
| Q7 | **Email:** which domain sends transactional mail, and do we get DNS access for SPF/DKIM? | Unverified domains land in spam — silently. | Client | 🔴 |
| Q8 | **Payments:** does the platform *collect* money online (Razorpay/UPI), or only *record* NEFT/UPI/cheque receipts? | The BRD says "records", but "Accounts/Payments" is ambiguous. A gateway adds reconciliation, refunds, webhooks and PCI-adjacent concerns — roughly a week. | Client | 🔴 |

## C. Existing systems & data — architecture-determining

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q9 | ~~Is the CRM the source of truth for stock and ledger?~~ **PARTLY ANSWERED 2026-08-14:** an ERP is *planned*, not live, and must eventually sync with the CRM. Handled by [ADR-019](Docs/Decisions.md) — seams now, connector later. Residual questions moved to §H. | Was the largest architectural unknown; now bounded. Schedule impact reduced from +1–1.5 weeks to ~1 day. | Client | 🟡 |
| Q10 | **Product master:** how many SKUs? Do we have HSN codes, GST slabs, UoM, MRP and per-tier price lists in a file? | REQ-004/005/203 cannot start without it. Also determines whether pricing is per-SKU or formula-based. | Client | 🔴 |
| Q11 | **Data migration:** what existing dealer, distributor, lead and customer data must move in? Format and volume? | Week 5 cutover depends on knowing this in Week 1, not Week 5. | Client | 🔴 |
| Q12 | **Invoicing:** does the platform issue **GST invoices** (with e-invoice/IRN and e-way bill), or only quotations and orders? | Legal exposure. E-invoicing is mandatory above the turnover threshold and integrating with the GSTN IRP is a week of work. The BRD mentions only quotes — needs explicit confirmation. | Client + their CA | 🔴 |

## D. Business rules — needed to write correct code

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q13 | **Hierarchy:** is Depot → Distributor → Dealer → Sub Dealer → Agent a strict tree? Can a dealer buy from two depots? Can a sub-dealer belong to two dealers? Can a customer be served by more than one dealer? | Tree vs graph is a schema-level decision. Getting it wrong means rebuilding the authorization layer. REQ-001/704. | Client | 🔴 |
| Q14 | **Lead priority scoring:** what are the actual weights for source quality, enquiry value, response time and engagement? What are the Hot/Warm/Cold thresholds? | REQ-106. We can propose a model, but the sales head must own it or it will be ignored in practice. | Client sales head | 🔴 |
| Q15 | **Won/Lost reasons:** confirm the fixed list. BRD suggests price, competitor, no response, product mismatch, financing not approved, out of area. Additions? Are sub-reasons needed? | REQ-109, and it drives REQ-1205 (Lost Lead Analysis). | Client | 🔴 |
| Q16 | **Approval limits:** what discount % can a Sales Manager approve? A Regional Manager? Above what value does it escalate to Management? Same question for scheme extensions, expenses and refunds. | REQ-305/803. The BRD says "up to defined limit" without defining it. | Client | 🔴 |
| Q17 | **SLA matrix:** response and resolution targets per complaint type and severity. Working hours or 24×7? Escalation path on breach? | REQ-801/802 and REQ-1210. SLA timers cannot be built against an undefined clock. | Client | 🔴 |
| Q18 | **Subsidy:** which schemes (PMKSY, state/iKhedut)? Is this tracking-only, or does it integrate with a government portal? Who updates approval status, and from what evidence? What are the disbursal stages? | REQ-501/502/503. Central to an irrigation business and currently the least specified area of the BRD. | Client | 🔴 |
| Q19 | **Rewards:** what qualifies a dealer for Gold/Silver/Bronze — volume, payment behaviour, ratings? Over what period? What is the actual gifting catalogue and budget? | REQ-401/402/1107. | Client | 🔴 |
| Q20 | **Territory master:** will the client supply the Gujarat state/district/taluka list, or do we import LGD codes from government open data? Is the business only in Gujarat today? | REQ-003/201/1208. Scheme scoping and every territory report depend on it. | Client | 🔴 |
| Q27 | **Targets:** how are sales targets set — per salesperson, per dealer, per territory, monthly or quarterly? Who enters them? | REQ-1203 (Target vs Achievement) has no data source otherwise. | Client | 🔴 |

## E. Product & UX

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q21 | **Location tracking:** is *continuous background* tracking a hard requirement, or is check-in/check-out at each visit sufficient? | Background tracking is **impossible in a PWA on iOS** and unreliable on Android. It requires a native Expo app — Phase 2. If it is a hard Week-5 requirement, the plan changes materially. | Client | 🔴 |
| Q22 | **Languages:** who supplies Hindi and Gujarati copy? Is Gujarati required on the dealer portal at launch, or English-first is acceptable? | REQ-1002. Machine translation on a professional B2B product reads badly; a human pass is needed. Client deliverable, due Week 4. | Client | 🔴 |
| Q23 | **Field connectivity:** do field staff and dealers work in areas with unreliable network? Is **offline** visit logging required? | Offline-first is a significant architectural addition and is not currently scoped. Better to know now. | Client | 🔴 |
| Q24 | **Consumer portal:** what does a farmer actually do there — check order status, raise a complaint, register a product, browse products? Is a public marketing site in scope, or separate? | REQ-1112 is the vaguest requirement in the BRD ("marketing/branding content and rating"). | Client | 🔴 |
| Q28 | **Devices:** what phones do dealers and field staff actually use? Android version floor? | Sets the performance and browser-support budget. Rural low-end Android is assumed. | Client | 🟡 assumed low-end Android, Chrome |
| Q29 | **Field app platforms:** Android only, or iOS too? Company-provided devices or personal (BYOD)? How many field users at launch? | iOS doubles the mobile track — separate build, separate signing, TestFlight or Apple Business Manager, separate QA on real devices. Android-only halves the mobile cost. | Client | 🔴 |
| Q30 | **Field app distribution:** public app stores, or internal distribution (signed APK / Play Internal App Sharing / Managed Google Play)? | **Now the longest external lead time in the project.** Google Play reviews background-location permission separately, needs a justification video, and routinely takes 2+ weeks with rejections. Internal distribution to employees bypasses store review entirely. Strong recommendation: internal. See [ISS-011](Docs/Issues.md). | Client | 🔴 |
| Q31 | **Farmer inside the dealer portal:** does a farmer log into the same application as distributors, or is it a separate light OTP mini-portal? What can a farmer actually do — orders, warranty, complaint, rating, all four? | A farmer and a distributor share almost nothing in navigation, vocabulary or data. Shared codebase is fine; shared interface is not. See [ISS-006](Docs/Issues.md). | Client | 🔴 |
| Q32 | **Permissions for the five undefined CRM roles:** Marketing, Accounts, Quality, Support and Admin are named users but have **no permissions defined anywhere** in the BRD. What can each View / Create-Edit / Approve / Delete, per module? | The BRD's own principle is "no module left with undefined access", yet its matrix covers only 4 of the 9 CRM roles. Blocks REQ-1301 and every module's RLS policy. **Highest-value single missing artefact.** See [ISS-005](Docs/Issues.md). | Client | 🔴 |

## F. Legal & compliance

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q25 | **DPDP Act 2023:** who is the Data Fiduciary? How is consent captured for farmer PII and WhatsApp messaging? What is the retention policy? Is employee location tracking covered by an employment policy and consent? | Farmer mobile numbers, addresses and payment data are personal data under Indian law. Employee location tracking without documented consent is a real exposure. REQ-605/705. | Client + legal | 🔴 |

## G. Testing, UAT & handover

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q33 | **Who signs UAT off**, and are real users (a sales exec, a real dealer) available for a testing week? | Code is gated by automated tests, but "does this match how we actually work?" can only come from real users. Without named UAT participants, sign-off becomes one person's opinion at the deadline. | Client | 🔴 |
| Q34 | Can we get **anonymised real data** — a few hundred real leads, dealers and orders — for realistic testing? | Realistic data exposes bugs that seeded data never will: 300-character dealer names, Gujarati text in every field, duplicate mobile numbers, historical records with missing fields. | Client | 🔴 |
| Q35 | Is there an existing system users are **migrating from**, and will both run in parallel for a period? | Parallel running changes the cutover plan and means data sync during the overlap. | Client | 🔴 |

---

## H. ERP, WhatsApp provider & scale — raised 2026-08-14

Arising from the client's answers on ERP, WhatsApp and user volume.

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q36 | **Which WhatsApp BSP does the client use?** Need: provider name, API docs, whether **inbound webhooks** are available on their plan, whether the 12 templates are already approved or we submit them, a sandbox/test number, and who pays per-conversation charges. | Removes Meta verification from the critical path — good — but BSP APIs are not interchangeable. If inbound webhooks are unavailable, **REQ-601 two-way conversation cannot be built** and we either upgrade their plan or fall back to Cloud API direct. Needed before Week 2. | Client | 🔴 |
| Q37 | **Which ERP, and when?** Vendor (Tally Prime / SAP B1 / Odoo / Zoho / Marg / other), and the expected go-live quarter. | Does not change Phase 1 — the seams are vendor-neutral by design. It changes what the seams are *shaped* for, and it tells us whether ERP integration is a Phase 2 conversation or a next-year one. | Client | 🔴 |
| Q38 | **Who owns and pays for the Supabase production instance?** Free/Nano cannot serve 100+ concurrent users — the connection ceiling alone rules it out. | A recurring client cost line (order of ₹2k–8k/month depending on tier) that must be agreed now, not discovered at go-live. Also determines who holds the production credentials. | Client + Nakul | 🔴 |
| Q39 | **Sign-off on the system-of-record ownership table** ([Architecture.md §10](Docs/Architecture.md)). | This is the actual anti-two-master mechanism. It determines which tables get sync columns and which get write constraints, so it must be settled **before the Week 1 schema freeze**. | Client | 🔴 |
| Q40 | **If the ERP will own tax invoicing, does the CRM issue only quotations and proforma?** | Would remove e-invoice/IRN and e-way bill compliance from Phase 1 entirely — a material scope reduction. Supersedes part of Q12. | Client + their CA | 🔴 |
| Q41 | **What issues GST invoices *today*, before the ERP exists?** | If nothing does, the CRM has to fill the gap in the interim and then hand over — the awkward case, and the one that needs planning rather than discovery. | Client | 🔴 |
| Q42 | **Of the 700–800 users, what is the split across the three applications?** Roughly how many internal CRM staff, how many portal partners, how many field-app devices? | Changes where load actually lands. 600 dealers on the portal is a very different system from 600 staff in the CRM — different caching, different query shapes, different peak profile. | Client | 🔴 |

## I. Raised by the client flowchart - 2026-08-17

From [Flowchart-Source.md](Docs/Flowchart-Source.md). Q43 is now the single most schedule-relevant open question in this document.

| # | Question | Why it matters | Owner | Status |
|---|---|---|---|---|
| Q43 | **Which states must be live at go-live?** The flowchart names eleven subsidy states with separate stage flows. Do all eleven need working subsidy pipelines in Phase 1, or does one state go live and the rest get configured afterwards? | The largest scope variable in the project. One state configured on a workflow engine fits inside 6.5 weeks. Eleven fully-detailed state pipelines does not, and no estimate holds until this is answered. See [ISS-019](Docs/Issues.md). | Client | 🔴 BLOCKING |
| Q44 | **"Language Friendly - not require" - confirm this means English only.** Read as written, multilingual UI is out of scope. | A genuine scope *reduction* of roughly 3-4 days, and it dissolves [ADR-008](Docs/Decisions.md) and [ISS-010](Docs/Issues.md). But we will not drop a documented BRD requirement on the strength of one ambiguous cell - confirm in writing. Note that field executives across eleven states are not uniformly comfortable in English. | Client | 🔴 |
| Q45 | **How many GST registrations, and in which states?** Which registration supplies which customer, and is there a depot-level GSTIN? | Determines whether the tax engine is single-seller or multi-seller. Rewrites [AC-203](Docs/Acceptance-Criteria.md) if multi. See [ISS-021](Docs/Issues.md). | Client + their CA | 🔴 |
| Q46 | **Full detail for at least one subsidy state.** Per stage: fields captured, documents required, who may advance it, what "In Query" resolution means, and the farmer-share formula. The sheet marks all of this "Detail Pending". | Stage names are not buildable. Needed before Week 3 or the workflow engine has nothing to validate against. [ISS-020](Docs/Issues.md). | Client | 🔴 |
| Q47 | **Confirm the vocabulary.** MIS System, System Material Value, Total MIS Cost, TPA, TR, FP, WO, C & D, Delivery Challan, Short Supply. | These become field names and status values in the frozen schema. Guessing that FP means Final Payment when it means Final Proposal produces a wrong model that is expensive to correct after freeze. Feeds [Glossary.md](Docs/Glossary.md). | Client | 🔴 |
| Q48 | **Commission rules.** Who earns commission, on what base (order value / collected payment / margin), at what rate or slab, when it accrues, when it becomes payable, who approves it, and is it calculated by the system or entered by Accounts? | Commission appears nowhere in the BRD and is money-critical. Not estimable until answered. [ISS-023](Docs/Issues.md). | Client | 🔴 |
| Q49 | **Where does State Head sit?** Above or beside Regional Manager? One per state? Is their approval required on every sales order, or only above a value threshold? | Third approver in the sales order chain, and a tenth CRM role. Changes the hierarchy closure table and the approval state machine. | Client | 🔴 |
| Q50 | **Depot and Institutional Sales - what are they?** Is a Depot a company-owned stocking location or a partner? Is Institutional Sales a channel, a customer type, or a team? And what is "Consumer/Employees" - staff purchase at concessional rates? | Determines whether these are hierarchy nodes, inventory locations, or customer categories. Cheap now, expensive after schema freeze. [ISS-022](Docs/Issues.md). | Client | 🔴 |
| Q51 | **How far does dealer-side inventory and invoicing go?** Do dealers record stock movements and upload invoice documents, or does the portal maintain a valued stock ledger and generate their GST invoices? | Roughly two weeks of scope sits between those two readings, and the second collides with the planned ERP. [ISS-026](Docs/Issues.md). | Client | 🔴 |
| Q52 | **Reward point redemption.** Is there a gift catalogue with point values? Who approves a redemption? Do points expire? Is the outstanding point balance a liability the client tracks? | Redemption appears on both the lead and the DMS sheets. Accrual is easy; redemption is an approval workflow with a fulfilment tail and a financial liability. | Client | 🟡 |
| Q53 | **Meeting-2 is "For Survey & Design" - what is produced?** A site survey form? A drip layout drawing? Is the design done in external software and attached, or expected inside the CRM? | If a design tool is expected inside the CRM, that is in no estimate anywhere. If it is "attach the drawing produced elsewhere", it is an upload field. The gap between those two readings is enormous. | Client | 🔴 |

## Assumptions we are proceeding on until told otherwise

Each of these is a decision we are making *for* the client because waiting would stall Week 1. **Each carries rework risk if wrong.**

| # | Assumption | Rework if wrong |
|---|---|---|
| A1 | ~~CRM is source of truth, no ERP sync~~ **Revised 2026-08-14:** CRM is source of truth in Phase 1; ERP is future and gets *seams*, not a connector ([ADR-019](Docs/Decisions.md)) | Low — seams are vendor-neutral. Risk is now concentrated in Q39 sign-off, not in the assumption |
| A2 | The platform issues **quotations and orders only**, not GST invoices with IRN | High — adds GSTN integration |
| A3 | Payments are **recorded**, not collected online | Medium — adds a gateway + reconciliation |
| A4 | The channel hierarchy is a strict tree, single-parent | Very high — authorization layer rebuild |
| A5 | Field tracking in Phase 1 is PWA check-in/check-out; background tracking is Phase 2 | Medium — a native app is a separate track |
| A6 | Business is Gujarat-only at launch; the model still supports multi-state | Low |
| A7 | Subsidy is **tracked** in the platform; no government portal integration | Medium |
| A8 | English ships complete at launch; Hindi and Gujarati keys wired, content follows | Low |

---

*Review this file at every Friday retro. A question that has been 🔴 for two consecutive weeks gets escalated in writing.*

<br>

---
---
---

<br>

# Z. Ask before project start

**This is the kickoff-call list.** Everything above is the complete register. These seven are the ones where a different answer produces a *materially different project* — different schema, different timeline, different contract. Ask these before a single line of code is written; the rest can be resolved during Week 1.

Ordered by how much damage a late answer causes.

---

### 1 · What runs stock, dispatch, invoicing and ledgers today?
*(Q9 · ISS-001 · affects REQ-1101, 1103, 1105, 1106)*

Tally, SAP, Busy, or spreadsheets? And is the CRM the **source of truth** for stock and ledger, or a **mirror** of that system?

**Why it must be first.** The dealer portal is roughly a third of the scope and rests entirely on this. If we build assuming the CRM owns stock and the answer turns out to be "Tally owns it, two-way", that is a rebuild of the order, stock and ledger modules plus 1–1.5 weeks of integration work currently in nobody's plan.

**Currently assumed:** CRM is the source of truth, no ERP sync in Phase 1 *(assumption A1)*.

---

### 2 · Does the platform issue GST invoices, or only quotations?
*(Q12 · ISS-002 · affects REQ-203)*

If invoices: are e-invoicing (IRN from the government IRP) and e-way bills in scope?

**Why it matters.** A quotation is a commercial document with no statutory obligations. A tax invoice has mandatory fields, an unbroken serial series, and above the turnover threshold — which this client almost certainly crosses — mandatory e-invoicing. These are different products with different legal exposure. Ask the client's **CA**, not only the client.

**Currently assumed:** quotations and orders only, no invoicing *(assumption A2)*.

---

### 3 · Is the channel hierarchy a strict tree?
*(Q13 · affects REQ-001, REQ-704 and every RLS policy in the system)*

Depot → Distributor → Dealer → Sub Dealer → Agent. Can a dealer buy from **two** depots? Can a sub-dealer belong to two dealers? Can one customer be served by more than one dealer?

**Why it matters.** Tree versus graph is a schema-level decision that the entire authorization layer is built on. Single-parent means a clean closure table and fast RLS. Multi-parent means a different data model and materially more complex permission logic. Discovering this in Week 3 means rebuilding authorization across ~25 tables.

**Currently assumed:** strict single-parent tree *(assumption A4 — flagged as the highest rework cost in the register).*

---

### 4 · Permissions for Marketing, Accounts, Quality, Support and Admin
*(Q32 · ISS-005 · affects REQ-1301 and every module)*

The BRD's RBAC table defines four CRM roles. You have since named **nine**. Five of them — Marketing, Accounts, Quality, Support, Admin — have no permissions defined anywhere.

**Why it matters.** The BRD's own stated principle is that no module is left with undefined or default access, and permissions are enforced in the database. Five undefined roles is five sets of RLS policies that cannot be written, and authorization is a Week 1 foundation, not a Week 4 addition. Under a test-gated model this is doubly critical: the permission test matrix is *generated* from this document, so an incomplete matrix means untested access paths.

**No assumption possible.** This one genuinely blocks Week 1.

---

### 5 · Field app — platform, devices, and distribution
*(Q21, Q29, Q30 · ISS-011 · affects REQ-701, 702, 703)*

Android only or iOS too? Company devices or personal? And — most importantly — **public app stores or internal distribution?**

**Why it matters.** Now that Field Sales is a native app, background location becomes technically possible, but Google Play reviews background-location permission *separately*, requires a justification video, and routinely takes 2+ weeks with rejections. That single review could outlast the build.

**Recommendation:** field staff are employees, not the public. Distribute internally — signed APK, Play Internal App Sharing, or Managed Google Play. No public listing, no store review, no background-location review gauntlet. Only iPhones in the fleet would change this.

---

### 6 · Subsidy — tracking only, or portal integration?
*(Q18 · ISS-008 · affects REQ-501, 502, 503)*

Which schemes (PMKSY, state / iKhedut)? Who updates approval status, and from what evidence? What are the disbursal stages, and how does a partially-disbursed subsidy interact with the farmer's outstanding balance?

**Why it matters.** For a micro-irrigation company in Gujarat this is a central workflow, and the BRD gives it three sentences. "Audit-ready record" — the BRD's own phrase — is not achievable against an undefined workflow, and this is exactly the kind of module where a guessed design has to be thrown away rather than adjusted.

**Currently assumed:** tracked in-platform, no government portal integration *(assumption A7)*.

---

### 7 · Is the deadline contractual, and does the client believe all 73 requirements land inside it?
*(Q1, Q2)*

Two separate questions, both commercial rather than technical:
- On the final day, what must be **true** — production live with real users, or UAT-ready on staging?
- Is there a **written, signed Phase 1 / Phase 2 split**, or does the client currently expect all 73 requirements?

**Why it matters.** This is the question that determines whether Week 6.5 is a launch or a dispute. Every other risk in this register can be managed. Misaligned scope expectations cannot be managed — they can only be surfaced early or discovered late.

---

> **If only one of these gets answered before kickoff, make it #4** — undefined permissions for five named roles blocks the Week 1 foundation outright, and unlike the others it has no safe working assumption.
