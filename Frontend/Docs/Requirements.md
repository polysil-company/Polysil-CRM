# Requirements Register — Polysil Irrigation CRM & Dealer Portal

**Source of truth:** `Polysil_Irrigation_CRM_Requirement_Enhanced.docx` (Loopify Solutions, rev 2, 11 Aug 2026). Verbatim extracted text archived at [BRD-Source.txt](Docs/BRD-Source.txt).

This register is the **contract**. Every task, branch, PR, test and doc references a `REQ-ID`. No code is written for a requirement that is not listed here. If the client asks for something not in this table, it becomes a new row with a new ID and an explicit tier — that is how scope creep is made visible instead of silently absorbed.

## Legend

| Field | Meaning |
|---|---|
| **Tier** | `P1` = in the 5-week contract MVP · `P2` = Phase 2 (post-launch) · `P3` = deferred backlog |
| **Status** | `SPEC` (business rule undefined, needs client answer) · `READY` (contract frozen, buildable) · `WIP` · `DONE` · `BLOCKED` (external dependency) |
| **Risk** | H/M/L — likelihood this row breaks the timeline |
| **Dep** | External dependency gating it — see [Open-Questions.md](Docs/Open-Questions.md) |

---

## 0. Platform Foundations (derived, not a BRD section — but mandatory)

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-000 | Authentication: email/password for internal staff, mobile OTP for dealers/agents/consumers | P1 | SPEC | M | Q6 |
| REQ-001 | Channel hierarchy model: Depot → Distributor → Dealer → Sub Dealer → Agent → Institutional → Consumer | P1 | SPEC | H | Q13 |
| REQ-002 | Org hierarchy model: Management → Regional/Area Manager → Sales Manager → Sales Executive | P1 | READY | M | — |
| REQ-003 | Territory master: State → District → Taluka (Gujarat first) | P1 | SPEC | M | Q20 |
| REQ-004 | Product & SKU master with HSN code, UoM, GST slab | P1 | SPEC | H | Q10 |
| REQ-005 | Price master: tiered price lists per channel level | P1 | SPEC | H | Q10 |
| REQ-006 | Generic approval engine (request → route → approve/reject → audit) | P1 | READY | M | — |
| REQ-007 | Generic notification engine (in-app, email, WhatsApp, SMS) with per-event templates | P1 | READY | M | — |
| REQ-008 | Activity/timeline event bus — every module writes to one customer timeline | P1 | READY | M | — |

## 2.1 Lead Generation & Marketing

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-101 | Lead Generation Management — central lead inbox with source, owner, stage, value | P1 | READY | L | — |
| REQ-102 | Auto Lead Capture (API) — Meta Lead Ads, Facebook + Instagram | P2 | BLOCKED | H | Meta App Review |
| REQ-103 | Auto Lead Capture (API) — website enquiry forms | P1 | READY | L | — |
| REQ-104 | Auto Lead Capture (API) — Google Ads / landing pages | P2 | BLOCKED | M | Q5 |
| REQ-105 | Marketing Activities — campaigns, exhibitions, dealer meets, promo drives, linked to leads | P1 | READY | L | — |
| REQ-106 | Lead Priority — auto Hot/Warm/Cold scoring from source, value, response time, engagement | P1 | SPEC | M | Q14 |
| REQ-107 | Duplicate Lead Detection — match on mobile, email, name+location; flag for review & merge | P1 | READY | M | — |
| REQ-108 | Cause of Multiple Leads — record and report every occurrence source per customer | P1 | READY | L | — |
| REQ-109 | Lead Won/Lost tracking with mandatory reason code + free-text note | P1 | SPEC | L | Q15 |

## 2.2 Scheme, Territory & Sales Tracking

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-201 | Scheme Management — state/district/taluka-scoped discount & promo schemes | P1 | SPEC | M | Q20 |
| REQ-202 | 3-Way Sales Tracking — Retail/B2C, Channel, Industrial/Institutional as separate pipelines | P1 | READY | M | — |
| REQ-203 | Instant Quote — product-wise, GST-calculated quotation generated in seconds | P1 | SPEC | H | Q10, Q12 |
| REQ-204 | Quote PDF generation + shareable link | P1 | READY | M | — |
| REQ-205 | Quotation lifecycle: Sent → Viewed → Accepted / Rejected / Negotiation / Expired → Follow-up | P1 | READY | L | — |
| REQ-206 | Full quotation history retained per customer | P1 | READY | L | — |

## 2.3 Task, Planning & Reminders

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-301 | Task Management — calls, visits, meetings, follow-ups against lead / dealer / complaint | P1 | READY | L | — |
| REQ-302 | Daily Work Planner — per-user day-wise schedule | P1 | READY | L | — |
| REQ-303 | Reminders & Notifications — email + SMS/WhatsApp for tasks, follow-ups, payment due, scheme expiry | P1 | READY | M | Q4, Q6 |
| REQ-304 | In-Out MOMs — minutes of meeting with action items tracked to closure | P1 | READY | L | — |
| REQ-305 | Approvals — discounts, scheme extensions, expenses routed to correct manager | P1 | SPEC | M | Q16 |

## 2.4 Rewards, Gifting & Feedback

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-401 | Reward System — dealer & team performance auto-qualifies reward tiers | P2 | SPEC | M | Q19 |
| REQ-402 | Gifting on Meet Category — gifting by dealer tier (Gold / Silver / Bronze) | P2 | SPEC | L | Q19 |
| REQ-403 | Services & Feedback — post-installation service requests + customer ratings | P1 | READY | L | — |

## 2.5 Subsidy & Farmer Payment Management

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-501 | Subsidy Management — track subsidy amount, approval status, disbursal separately from customer payment | P1 | SPEC | H | Q18 |
| REQ-502 | Farmer Payment Tracking — ledger of advance, subsidy portion, balance due, final settlement | P1 | SPEC | H | Q9, Q18 |
| REQ-503 | Audit-ready subsidy report: who is paid, what is pending, what is outstanding | P1 | SPEC | M | Q18 |

## 2.6 WhatsApp Integration

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-601 | Official WhatsApp Business API connection | P1 | BLOCKED | H | Q4 |
| REQ-602 | Lead & sales messaging: lead ack, quote share, order confirm, payment reminder | P1 | BLOCKED | H | Q4 |
| REQ-603 | Complaint & support messaging: registration, status update, resolution | P1 | BLOCKED | H | Q4 |
| REQ-604 | WhatsApp Lead Dashboard — unified inbox, assign & respond, tied to CRM record | P1 | BLOCKED | H | REQ-601 |
| REQ-605 | Opt-in consent capture & storage per contact (DPDP Act + Meta policy) | P1 | READY | M | — |

## 2.7 Field Sales App, Location Tracking & Team Hierarchy

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-701 | Field app: visit check-in / check-out with GPS coordinates + photo | P1 (PWA) | SPEC | M | Q21 |
| REQ-702 | Live / continuous background location tracking & route history | P2 (native) | SPEC | H | Q21 |
| REQ-703 | Sales Manager view — team visits, locations, task completion, performance on map | P1 (web) | SPEC | M | Q21 |
| REQ-704 | Hierarchy-level role-based data scoping | P1 | READY | H | REQ-002 |
| REQ-705 | Employee location-tracking consent + privacy notice | P1 | SPEC | M | Q25 |

## 2.8 Customer Support Module

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-801 | Complaints — log, assign, track raise→resolution with SLA timers, customer-visible status | P1 | SPEC | M | Q17 |
| REQ-802 | Dealer ↔ Customer ↔ Quality Assessment routing workflow | P1 | SPEC | M | Q17 |
| REQ-803 | Refund Approval Workflow post quality assessment | P1 | SPEC | M | Q16 |
| REQ-804 | Warranty Tracking — status, start/end dates, claim history per unit sold | P1 | SPEC | M | Q12 |
| REQ-805 | New Change / Replacement Tracking | P1 | READY | L | — |
| REQ-806 | Rating System — dealers & customers rate service, installation, product quality | P1 | READY | L | — |

## 2.9 360° Customer & Channel View

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-901 | Unified Customer Timeline joining calls, visits, WhatsApp, quotes, follow-ups, complaints, payments, schemes, rewards, ratings | P1 | READY | M | REQ-008 |
| REQ-902 | Loss / Drop-off Point Identification — stage + elapsed time at which customer was lost | P1 | READY | M | — |
| REQ-903 | Improvement Insight — recurring pattern surfacing from quote history + won/lost reasons | P2 | SPEC | M | — |

## 2.10 Dashboard & Usability

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-1001 | Role-tailored dashboard: lead funnel, pipeline value, task reminders, scheme performance, dealer leaderboard | P1 | READY | M | — |
| REQ-1002 | i18n — English (P1), Hindi + Gujarati (P1, content supplied by client) | P1 | SPEC | M | Q22 |

## 3. Dealer / Customer Relationship Portal

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-1101 | Sales Order against live pricing & stock availability | P1 | SPEC | H | Q9 |
| REQ-1102 | Material Planning — forward stock & advance planning | P2 | SPEC | H | Q9 |
| REQ-1103 | Dispatch Tracking — order confirmed → delivered | P1 | SPEC | H | Q9 |
| REQ-1104 | Pricing & Discounting — tiered by channel level, active schemes auto-applied | P1 | SPEC | H | Q10 |
| REQ-1105 | Stock Management — live stock across depots/warehouses, low-stock indicators | P1 | SPEC | H | Q9 |
| REQ-1106 | Accounts / Payments — dealer ledger, NEFT / UPI / cheque records | P1 | SPEC | H | Q8, Q9 |
| REQ-1107 | Rewards (Gifting) — dealer-side eligibility & status visibility | P2 | SPEC | L | REQ-401 |
| REQ-1108 | Rating System tied to accounting & reconciliation | P1 | READY | L | — |
| REQ-1109 | Adding Agent — dealer manages own agents under correct hierarchy | P1 | READY | M | REQ-001 |
| REQ-1110 | Complaints & Tracking from dealer, feeding the same support module | P1 | READY | L | — |
| REQ-1111 | Promotional Activities Support — running schemes & promo material visibility | P1 | READY | L | — |
| REQ-1112 | Customer Relationship Portal — mobile-number based consumer capture, branding content, rating | P1 | SPEC | M | Q24 |

## 4. Reports & Analytics

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-1201 | Lead Conversion Report — stage funnel, conversion % by source / salesperson / territory | P1 | READY | M | — |
| REQ-1202 | Salesperson Performance Report | P1 | READY | M | — |
| REQ-1203 | Target vs Achievement Report (real-time) | P1 | SPEC | M | Targets master |
| REQ-1204 | Sales Forecast Report — from open pipeline, quote stage, historical conversion | P2 | SPEC | M | — |
| REQ-1205 | Lost Lead Analysis Report | P1 | READY | L | — |
| REQ-1206 | Follow-up Pending / Overdue Report with ageing | P1 | READY | L | — |
| REQ-1207 | Dealer Performance Report | P1 | READY | M | — |
| REQ-1208 | Territory Performance Report | P1 | READY | M | — |
| REQ-1209 | Campaign Performance Report vs campaign cost | P2 | SPEC | M | — |
| REQ-1210 | Complaint / SLA Report — volume, resolution vs SLA, repeat rate, refund outcomes | P1 | READY | M | — |
| REQ-1211 | Export to CSV / Excel / PDF on every report | P1 | READY | L | — |

## 5. Roles, Permissions & Audit

| ID | Requirement | Tier | Status | Risk | Dep |
|---|---|---|---|---|---|
| REQ-1301 | RBAC matrix — every role × module defined for View / Create-Edit / Approve / Delete, no defaults | P1 | READY | H | — |
| REQ-1302 | Full audit trail: user, timestamp, module, old value → new value, on every Create/Update/Approve/Reject/Delete | P1 | READY | H | — |
| REQ-1303 | Audit log append-only, read-only below Management, non-tamperable | P1 | READY | H | — |
| REQ-1304 | Soft delete everywhere; hard delete only by Management, always with an audit entry | P1 | READY | M | — |

---

## Coverage summary

| Bucket | Count |
|---|---|
| Total requirements | 73 |
| P1 — inside the 5-week contract | 62 |
| P2 — Phase 2 | 11 |
| Currently `BLOCKED` on an external dependency | 6 |
| Currently `SPEC` — business rule undefined | 33 |

> **33 of 73 requirements have undefined business rules today.** Contract-first means we do not start these. Converting `SPEC` → `READY` is the single highest-leverage activity of Week 0, and it is client-side work, not ours.
