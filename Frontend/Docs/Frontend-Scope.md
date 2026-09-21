# Frontend Scope — Polysil CRM/DMS

**Version:** v0.3 · **Date:** 2026-09-14
**Supersedes:** v0.2 (2026-09-06), and the three-app / full-stack model in [Plan.md](Plan.md) and [Architecture.md](Architecture.md).
**Pre-pivot state is preserved in** [Contexttill6Sept2026.md](Contexttill6Sept2026.md).
**How it is built:** [Frontend-Architecture.md](Frontend-Architecture.md) · [Design-System.md](Design-System.md)

> **The one-line version.** Backend is no longer ours. We build **one web application** (public
> website + CRM + channel partner access, all in one codebase, split by role). The mobile app for
> field staff comes later. Internal roles plus one channel-partner role with three types; everything
> is role-driven and region-scoped.

---

## 1. What changed

### On 6 September

| Before | Now |
|---|---|
| We own the database, RLS, auth, API, integrations | **A backend developer owns all of it.** Postgres. Out of our scope. |
| Three applications (CRM, Dealer Portal, Mobile) | **One web app** — roles decide what you see. Plus mobile (later). |
| Mobile route tracking, background location | **Punch in / punch out.** Locations, total distance, total time. |
| English / Hindi / Gujarati | **English only.** |
| Social media lead capture | **Dropped.** Six sources only. |
| WhatsApp — provider unknown, verification pending | **Client already has the API.** |
| Subsidy = 10–14 weeks of calculation + statutory documents | **Backend developer owns the logic.** We build forms and display. |
| ~14 roles, some undefined | **Defined roles** (see §2). |
| Seven separate approval chains | **One rule: amount-based auto-escalation.** |
| No public website | **New: small public site with phone-number entry** |
| — | **New: AI chatbot** (OpenRouter) for basic queries and navigation |
| — | **New: email integration** (Resend or Zoho) |

### On 14 September

| Question in v0.2 | Decision |
|---|---|
| Is the "Dealer" in role 1 the same as role 6? (Q1) | **No.** Role 1 is defined by what employees see and access. Dealers are a completely separate role with **completely different views**. |
| Is the channel hierarchy flat? (Q2) | **No.** One umbrella role with **three types: Distributor, Dealer, Sub-Dealer.** The umbrella name is still to be chosen. |
| Approval thresholds (Q3) | **Amounts come later from the backend.** The **Account, QA and Dispatch gates apply only when the request comes from a State Manager.** |
| Who owns Marketing and Schemes? (Q4) | **Admin sets both.** **Marketing is visible to channel partners only; Schemes are visible to everyone.** |
| Mobile app | **Deferred.** The web foundation comes first. |
| Icons | **Hugeicons (free set)**, not Lucide. |
| Components | **shadcn/ui on Base UI**, restyled to our own design system. |

Also: no separate "sales person" role. Polysil's own employees use the CRM; some do field work, and
that field work is part of the same system.

---

## 2. Roles

| # | Role | Scope | Shape of their UI |
|---|---|---|---|
| 1 | Employee (field officer) | Own records | Full working surface — leads, quotations, orders, complaints, tasks. Later: mobile app user. |
| 2 | District Manager | District | Role 1 + approvals up to a limit + assign tasks + team reports |
| 3 | State Manager | State | Same, wider scope, higher limit. **Requests they raise also pass the Account, QA and Dispatch gates.** |
| 4 | Regional Manager | Region | Same, wider scope, higher limit |
| 5 | Admin | Everything | All of the above + masters + users + roles + **sets Marketing and Schemes** + thresholds |
| 6 | Account Manager | Global · **1 person** | A work queue — payments, ledgers, financial approval |
| 7 | Dispatch Manager | Global · **1 person** | A work queue — dispatch, stock, delivery status |
| 8 | QA Manager | Global · **1 person** | A work queue — complaint quality check, approve/reject replacement |
| 9 | **Channel partner** *(name TBD)* — types **Distributor · Dealer · Sub-Dealer** | Own relationship with Polysil | **Completely different views:** their leads, their orders, Polysil stock available to them, ledger, **marketing offers**, schemes, rewards, complaints |

**Two rules govern the whole UI:** *role-based permission* (what you can do) + *region-based views*
(what you can see). Every list, report and dropdown is filtered by both.

**Visibility of Marketing and Schemes:**

| | Admin | Internal roles | Channel partners |
|---|---|---|---|
| Marketing offers | Creates and manages | Not visible | **Visible** |
| Schemes | Creates and manages | **Visible** | **Visible** |

> Roles 6, 7 and 8 are **one person each with global scope** — essentially one work queue apiece.

In code: the backend returns each user's permissions from `GET /auth/me`, and the UI gates on them
(`src/lib/auth/permissions.ts`). The mock backend follows the rules above in
`src/mocks/data/permissions.ts`.

---

## 3. What we are building

### 3.1 The web application — one codebase

```
src/app/
├── (site)/     ← public: information, Product Master, phone-number entry (later — SITE-001)
└── (app)/      ← everything behind a login, role-gated
```

The channel partner portal is **not a separate application**: a channel partner logs into the same
app and sees their own set of screens. One design system, one session, one deploy.

### 3.2 The mobile app — deferred

Expo / React Native, Android-first, internally distributed. Lead capture, sales order, complaint,
feedback, daily tasks, verification and survey, and **punch in / punch out** with foreground location
only. Planned after the web foundation and first modules.

### 3.3 What we are *not* building

Database, migrations, row-level security, authentication, the API, WhatsApp and email sending,
subsidy calculation, approval threshold logic, cron jobs, backend deployment, ERP seams.

---

## 4. Platform and tech stack (web)

Full table with versions and reasons: [Frontend-Architecture.md §1](Frontend-Architecture.md).

| Concern | Choice |
|---|---|
| Framework | **Next.js 16.3**, App Router, React 19.3 |
| Language | **TypeScript 6, strict** |
| Styling | **Tailwind v4** with a single token file, **shadcn/ui on Base UI** |
| Icons | **Hugeicons** (free) |
| Tables | **TanStack Table v9** |
| Server state | **TanStack Query** |
| Forms | **react-hook-form + Zod** |
| URL state | **nuqs** |
| Animation | **CSS transitions + Motion**, directional page transitions with React `<ViewTransition>` |
| Mocking | **MSW**, with switchable scenarios and roles |
| Component preview | **Storybook 10** |
| Tests | **Vitest**, **Testing Library**, **Playwright + axe** |
| AI | **OpenRouter** through a Next.js route handler — the key never reaches the browser |
| Errors | Logger now; **Sentry or GlitchTip** when hosting is decided |
| Hosting | **VPS via Dokploy** alongside the backend — or Vercel. *To decide.* |
| Charts | Deferred until the reports module |
| Maps | **MapLibre GL** + free tiles, with the mobile scope |

API types: agreed Zod schemas today; generated from the backend's **OpenAPI spec** when it exists.

---

## 5. The work, in plain language

### 5.1 Public website
Information pages. **Product Master shown from the database** — the main reason the site exists.
Entry is by typing a phone number; there is nothing personal behind it, so it is a soft gate that also
captures a number, not real authentication. Responsive and fast — many channel partners open it on a phone.

### 5.2 Lead Generation & Management
The heart of the product.

- **Capture from six sources** — WhatsApp, website form, employee entry, QR code, phone/email, offline.
- **Assignment** down the hierarchy, and reassignment.
- **Status movement** with a history of who changed what and when.
- **Lost** → reason and date, nothing more.
- **Won** → creates a Sales Order.
- **Quotation lives inside the lead.** You quote from the lead; a quotation is valid 45 days.

### 5.3 The five types
**Subsidised · Commercial · Industrial · Export · Complaint.** The type changes which fields and which
quotation template you get. *Complaint* being a type is how a verified complaint becomes a replacement order.

### 5.4 Quotation
Template-driven, one template per type. Line items, product picker, quantity, rate, discount, tax.
Preview and download. Version history — quotations get revised.

### 5.5 Sales Order
From a won lead or directly. Party details, items, dispatch information, payment terms.

### 5.6 Approvals — one mechanism
**Approval is driven by amount.** If the value exceeds the approver's limit it moves automatically to
the next person up the ladder. **Thresholds come from the backend** (amounts to be provided).
**When the request is raised by a State Manager**, it also passes the **Account, QA and Dispatch** gates.

One reusable piece of UI, used by quotations, orders, complaints and discounts:
- an **approval inbox** — everything waiting on me, with the amount and why it escalated
- an **approval trail** on every document — who approved, at what level, when, and which gates applied
- a **threshold screen** in admin

### 5.7 Complaints
Raise → manager approval → **QA Manager quality check** → replacement order (type: Complaint), for the
complained items only.

### 5.8 Marketing & Promotional
Offers Polysil puts out. **Admin** creates them, sets the audience and validity. **Visible to channel
partners only.**

### 5.9 Schemes
Same shape as offers — definition, validity window, audience, and who used it. **Admin** creates them.
**Visible to everyone.**

### 5.10 Tasks & Daily Work
Assignment down the hierarchy — a manager assigns to whoever reports to them. Daily planner, due dates,
completion, and a "what is my team doing today" view.

### 5.11 Channel partners
List and detail per partner and type (distributor, dealer, sub-dealer). Their relationship with Polysil:
orders placed, Polysil stock available to them, ledger, offers, reward points and redemption.

### 5.12 Masters
Products, stock, MRP, price lists, territories, users, roles, approval thresholds.

### 5.13 Reports & Dashboards
Role-scoped and region-scoped. The screen a Regional Manager sees is the same component a District
Manager sees with a narrower filter. Excel export throughout; PDF where the client later asks.

### 5.14 Subsidy
**Backend owns the calculation.** We build the forms, show the computed figures, and display case status.

### 5.15 Admin
Create and deactivate accounts, assign roles and channel partner types, set approval thresholds, manage
Marketing and Schemes. And the lead-handover flow when an employee leaves — see §7.

### 5.16 AI chatbot
A panel in the CRM. OpenRouter, fed with CRM structure and help content, answering basic questions and
navigation. Streaming response. Not an agent that takes actions. **The key stays on the server.**

### 5.17 Notifications
WhatsApp (their API) and email (Resend or Zoho) — backend sends them. Our work is the template management
screen and showing message history against a lead or customer.

**In-app (NOTIF-001, NOTIF-002):** a bell in the top bar with the unread count and the latest
notifications — approvals waiting on me, leads and tasks assigned to me — each opening its record where
a screen exists. Built against a proposed contract and mocks; polled every 30 s until the backend picks
a push transport.

### 5.18 Messages
Direct, one-to-one conversations **between staff** (MSG-001 … MSG-005). Channel partners have none. A
message can carry a link to a lead — "Share with a colleague" on a lead's page. Built against a proposed
contract and mocks; the conversation list polls every 30 s and the open conversation every 10 s.

---

## 6. How we avoid blocking each other

Not the screen count — **the API contract** decides whether this works.

1. **Agree the contract before either side builds** — endpoints, request and response shapes, error
   format, pagination, auth header, date and money formats. We propose RFC 9457 errors.
2. **One Data ID per functionality, shared by both sides** ([Data-IDs.md](Data-IDs.md)) — every request
   carries `x-data-id` and `x-request-id`.
3. **Mock every endpoint from day one (MSW).** The frontend runs at full quality before a single real
   endpoint exists. When an endpoint lands, we switch the environment, not the code.
4. **A shared, frozen seed dataset** — the same fake data in the staging database and our mocks.
5. **Contract violations are logged, not guessed at.** A response that breaks the agreed shape shows up
   as `CONTRACT_VIOLATION` with the failing fields.
6. **Three environments:** feature branch (mocks) → integration/staging (real staging API, tested
   together) → production ([Environments.md](Environments.md)).

---

## 7. Lead handover when an employee leaves

When an employee leaves, their leads go to **the channel partner who originally brought that lead**.

**Recommendation — no extra role.** What is needed:

- a lead remembers **which channel partner sourced it** (a field — already in the leads contract)
- a lead can be **assigned to a channel partner**, not only to an employee
- the partner's permission on an assigned lead moves from **read-only to edit**
- a **bulk reassignment screen** in admin: pick a departing employee, see their open leads, route each to
  its sourcing partner or to another employee

*Still to confirm with the client.*

---

## 8. Foundation status — 14 September

Built and ready to extend (details in the changelog):

- Design system: one token file, light and dark themes, motion rules, lint enforcement
- Component library: restyled shadcn/Base UI primitives and CRM patterns, each previewable in Storybook
- App shell: role-filtered sidebar, header, command menu (⌘K), mobile menu, directional page transitions
- Leads (mocked): list with search, filters, sorting, pagination, selection; New Lead form; lead detail
- Dashboard (mocked): KPIs, pipeline, follow-ups, sources
- Logger with runtime log level; Data ID system; API client with contract validation
- Mock backend with scenarios and role switcher; unit, Storybook and end-to-end test setup
- AGENTS.md rules, changelog system, commit rules, CI

---

## 9. Rough size

| | Screens |
|---|---|
| Public site | ~5 |
| Auth | 2 |
| Leads | 4 |
| Quotation | 4 |
| Sales Order | 3 |
| Complaints + QA queue | 4 |
| Approvals (inbox, trail, thresholds) | 3 |
| Tasks | 3 |
| Marketing & Schemes | 6 |
| Channel partners | 4 |
| Masters | 6 |
| Reports & dashboards | ~8 |
| Subsidy forms | 3 |
| Admin (users, roles, handover) | 3 |
| Chatbot | 1 |
| **Web total** | **~59** |
| **Mobile (later)** | **~11** |

---

## 10. Open questions

**Blocking the next modules**

1. **Umbrella name for the channel partner role** (Distributor · Dealer · Sub-Dealer). "Channel partner"
   is a placeholder.
2. **Do the three partner types see different screens from each other**, or the same screens with
   different data and limits?
3. ~~**Auth design**~~ — **Answered by the backend contract (15 September 2026):** staff use email and
   password, channel partners a one-time code; a short-lived bearer token plus an httpOnly refresh
   cookie; the API sits on the app's origin. See Frontend-Architecture §8.
4. **API contract session** — when, and will staging have the shared seed data?
5. ~~**Money unit**~~ — **Answered by the backend contract (21 September 2026):** rupees as decimal
   strings (`"125000.00"`). The frontend formats them as they are and adds them in whole paise
   (`sumRupees`), never in floating point.
6. ~~**Error format**~~ — **Answered by the backend contract:** `{ error: { code, message, fields? } }`,
   where a 422's `fields` maps each field path to its reason. Problem details are still read, for
   proxies and gateways.

**Needed soon**

7. **Approval threshold amounts** per role (backend will provide).
8. **Phone entry on the website — OTP or just a number?**
9. **Punch in / punch out — what exactly is measured?** (mobile scope)
10. **Hosting** — same VPS through Dokploy, or separate?
11. **Subsidy forms** — fields to capture and what the backend returns.
12. **GST invoices, or only quotations and sales orders?**
13. **Brand assets** — logo, colours, typeface approval (the design tokens make this a small change).

**Asked of the backend for leads (22 September 2026)** — the lead screens run on the dev API; these
gaps show as "—" or have no effect until they land:

14. **Sorting on `GET /leads`** (LEAD-001) — `sort` = `created_at` | `farmer_name` |
    `estimated_value`, `order` = `asc` | `desc`, keeping keyset paging (the cursor would carry the sort
    key). The table's sort arrows already send these; today the list is always newest first.
15. **Next follow-up date** on a lead (LEAD-001, LEAD-003) — the Follow-up column and field.
16. **Crops and land (acres)** on a lead (LEAD-003) — captured on field visits.
17. **Win probability and weekly activity** (LEAD-001, LEAD-003) — or confirm the `score` replaces
    win probability, and the timeline replaces weekly activity, so the columns can go.
18. **Which territory levels a lead may sit in** (LEAD-002) — the docs say "taluka or district", but
    the picker's search also returns villages and the state. Should the API refuse those, or filter
    them from `GET /lookups/territories`?

**Deferred by the client**

- Which documents need PDF and which need Excel. A single export mechanism keeps adding one small.
