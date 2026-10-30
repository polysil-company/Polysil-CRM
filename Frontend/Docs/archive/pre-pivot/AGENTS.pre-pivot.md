# AGENTS.md — Operating Constraints for AI Contributors

**Read this file completely before writing a single line of code. It overrides your defaults.**

This codebase is built by four models — Claude Opus 5, Claude Sonnet 5, GPT 5.6 Sol, GPT 5.6 Luna — working in parallel under one human architect (Nakul Srivastava). It is production software for a client with a valuation in the crores. The constraints below exist because parallel AI contribution without hard boundaries produces four architectures in one repository.

---

## 0. How to engage — always push back

**In every conversation, discussion, or decision on this project: always feel free to push back, disagree, and suggest better ideas, approaches and alternatives.** If you think a decision in `Docs/` is wrong, say so — with reasoning and a concrete alternative. If a requirement seems to solve the wrong problem, say that too. If you see a simpler path, propose it.

Agreement that is merely compliant is worthless here. A rule you follow while believing it is wrong is a bug waiting to happen, and silence in that moment costs more than the disagreement would have.

Two boundaries on this:
- **Push back in discussion, not in implementation.** Once a decision is recorded in [Decisions.md](Docs/Decisions.md) as `ACCEPTED`, build it as decided — and open a superseding ADR if you still disagree. Do not relitigate a settled decision by writing code that quietly does something else.
- **Bring an alternative, not just an objection.** "This is wrong" is noise. "This is wrong because X, and Y handles it better at cost Z" is useful.

This applies to §1–§10 below as much as to anything else. If a constraint in this file is getting in the way of good work, say so.

---

## 1. The Prime Directives

1. **You may not invent requirements.** If it is not a `REQ-ID` in [Requirements.md](Docs/Requirements.md), you do not build it. Not "while I was here", not "this seemed obviously needed".
2. **You may not modify a FROZEN layer.** See §3. If your task appears to require it, **stop and report** — do not work around it.
3. **You may not guess a business rule.** If a scoring weight, approval limit, SLA duration, tax treatment or hierarchy rule is not written in `Docs/`, stop and report. A guessed rule that ships is worse than a blocked task.
4. **You may not leave a task partially done and call it done.** Report exactly what is incomplete and why.
5. **One `REQ-ID` per branch, per PR.** Branch name: `feat/REQ-203-instant-quote`.
6. **Tests are the gate, not code review.** Implementation code is not reviewed line by line on this project — a passing acceptance suite is what makes a requirement shippable. That places the entire burden of correctness on tests, which is why §6 and [Testing.md](Docs/Testing.md) are enforced strictly rather than aspirationally. **You do not write the tests for your own feature** — see §2.

---

## 2. Model routing

| Model | Owns | Never assigned |
|---|---|---|
| **Claude Opus 5** | Schema & migrations · RLS policies · `contracts/` · service-layer signatures · GST engine · hierarchy/closure logic · audit system · architecture decisions · reviewing other models' PRs | Bulk CRUD screens (waste of capability) |
| **Claude Sonnet 5** | Feature modules cloned from the reference slice · CRUD screens · forms · data tables · Playwright specs · i18n key extraction | Schema, RLS, contracts, money logic |
| **GPT 5.6 Sol** | Reports & analytics SQL · materialized views · data transformation · export (CSV/XLSX/PDF) · seed data generation | Auth, RLS, payment/subsidy logic |
| **GPT 5.6 Luna** | Integration adapters (WhatsApp, SMS, email, webhooks) · notification templates · cron/Edge Functions · retry & queue logic | Schema, RBAC, financial calculations |
| **Nakul (human)** | UI/UX, design system, visual polish, animation, contract-layer review, all merges, all client-facing decisions | — |

> Anything touching **money, tax, subsidy, permissions or audit** is Opus 5 or Nakul. No exceptions. These are the four areas where a subtle bug becomes a legal or financial problem rather than a UX problem.

### Adversarial test pairing — mandatory

**The model that implements a feature never writes that feature's tests.** If the same model does both, a misunderstood requirement produces a wrong implementation *and* a test that confirms the wrong behaviour — the suite goes green and nothing was verified ([ISS-012](Docs/Issues.md)). Since implementation code is not human-reviewed here, that failure mode would be undetectable.

| Feature built by | Its tests written by |
|---|---|
| Sonnet 5 | GPT 5.6 Sol |
| GPT 5.6 Sol | Sonnet 5 |
| GPT 5.6 Luna | Sonnet 5 |
| Opus 5 | GPT 5.6 Sol, plus generated matrices |

The test author works from the **acceptance criteria in [Acceptance-Criteria.md](Docs/Acceptance-Criteria.md)** and from the requirement — never by reading the implementation. If the criteria are ambiguous, that is a BLOCKED report (§8), not a look at the source.

---

## 3. Frozen layers

| Path | Status | Who may edit |
|---|---|---|
| `supabase/migrations/**` | ⛔ FROZEN | Opus 5 / Nakul, via ADR |
| `src/contracts/**` | ⛔ FROZEN | Opus 5 / Nakul, via ADR |
| `src/server/db/**` | ⛔ FROZEN | Opus 5 / Nakul |
| `src/server/services/*.ts` — **signatures** | ⛔ FROZEN | Opus 5 / Nakul. Bodies may be implemented by the assigned model; the exported signature may not change |
| `src/components/ui/**` | ⛔ FROZEN | Nakul |
| `src/lib/rbac.ts`, `src/lib/hierarchy.ts` | ⛔ FROZEN | Opus 5 / Nakul |
| `Docs/Decisions.md` | append-only | anyone may append a `PROPOSED` ADR; only Nakul marks `ACCEPTED` |
| everything else | free | assigned model |

**If a frozen layer is wrong, that is a finding, not an obstacle.** Report it in the PR description under `## Contract issue` and stop.

---

## 4. Non-negotiable code standards

Derived from the project owner's standing engineering rules. CI enforces most of these; the rest are review-blocking.

### TypeScript
- `strict: true`. **No `any`.** No type assertions unless genuinely unavoidable, and then with a comment explaining why.
- Explicit return types on every exported function and component.
- Zod validates every boundary: API routes, Server Actions, webhooks, form input, external API responses. **Parse, don't cast.**
- Types are derived (`z.infer`, `Database['public']['Tables']`), never hand-duplicated.

### React / Next.js
- App Router. Server Components by default; `"use client"` only where interactivity genuinely requires it, and as deep in the tree as possible.
- Data fetching in Server Components or Server Actions. **Never in `useEffect`** unless truly unavoidable — and then with a comment.
- `next/image` for all images. Never a raw `<img>`.
- Functional components and hooks only.

### Styling
- Tailwind utility classes only. No inline styles, no CSS modules, no custom CSS unless Tailwind genuinely cannot express it.
- **Mobile-first**: base styles first, then `sm:` / `md:` / `lg:`. The dealer portal is used on low-end Android phones in the field — that is the primary target, not the desktop.
- Design tokens from the design system. No hard-coded hex values, no arbitrary spacing values outside the scale.

### Accessibility
- Semantic HTML: `<button>` not `<div onClick>`, `<nav>`, `<main>`, `<table>` for tabular data.
- Every interactive element: accessible name, correct role, full keyboard operation, visible focus ring.
- Target WCAG 2.2 AA. Forms have associated labels and `aria-describedby` error messaging.

### Animation
- Framer Motion only. Purposeful motion only — state transitions, feedback, spatial continuity. No decoration on data-dense CRM screens.
- Always honour `prefers-reduced-motion`.

### Every screen ships all states
Loading · empty · error · disabled · success · offline · permission-denied · mobile. A screen missing any applicable state is not done.

---

## 5. Security rules

1. RBAC is enforced by **RLS in Postgres**. UI-level checks are cosmetic and never sufficient.
2. The Supabase **service-role key never reaches the client** and is used only in server code where RLS must be bypassed deliberately — each such use carries a comment explaining why.
3. Every mutation produces an audit trail entry. If your feature bypasses the audit trigger, that is a bug.
4. **Never log PII** — farmer names, mobile numbers, addresses, payment details. Sentry scrubbing is configured; do not defeat it.
5. Webhooks verify signatures before parsing. Public endpoints are rate-limited.
6. Secrets come from env vars. Never commit a secret, never write one into `Docs/`, never print one in a log.

---

## 6. Definition of Done

A `REQ-ID` is done only when **all** of these hold. State each explicitly in your PR description. Because there is no line-by-line review behind this list, the list *is* the quality system — treat a skipped item as a shipped defect.

- [ ] Every acceptance criterion for this REQ-ID has a passing automated test
- [ ] Tests were written by the paired model (§2), from the criteria — not by me, not from my code
- [ ] Scenario coverage from [Testing.md](Docs/Testing.md) §5 applied: empty · single · boundary · large values · Unicode (Gujarati/Hindi) · nulls · illegal state transitions · permission-denied · integration failure · offline/slow network
- [ ] `npx tsc --noEmit` — zero errors
- [ ] `npx eslint .` — zero warnings (no disable comments without a justification comment)
- [ ] `npx vitest run` — green, with new tests for any business logic added
- [ ] Zod validation on every input boundary
- [ ] RLS policy written **and tested**, including the negative cases, for the new tables/columns
- [ ] Audit entry verified for every mutation
- [ ] All applicable UI states implemented
- [ ] Verified at 360px and 1440px
- [ ] Accessibility: keyboard path + accessible names verified
- [ ] i18n: no hard-coded user-facing strings; keys added to `en.json` (and `hi`/`gu` stubs)
- [ ] No unused imports, variables, or dead code
- [ ] Row updated in [Requirements.md](Docs/Requirements.md); module entry added to [Documentation.md](Docs/Documentation.md)
- [ ] Listed which existing components/modules this change could affect

---

## 7. Required PR description format

```markdown
## REQ-ID
REQ-203 — Instant Quote

## What I changed
[FileName.tsx (lines 51-81)](src/path/FileName.tsx:51): explanation.
[other.ts (line 22)](src/path/other.ts:22): explanation.

## Business rules applied
Cite the Docs source for each rule. If a rule was not documented, this section says BLOCKED.

## Acceptance criteria → tests
| AC | Test file | Status |
|---|---|---|
| AC-203-01 | `gst.service.test.ts:44` | ✅ |
Written by: <paired model>. Every AC must map to a test, or be listed as not-covered with a reason.

## Scenario coverage
Which of the Testing.md §5 categories apply, and where each is covered.

## Contract issue
(only if a FROZEN layer appeared to need changing — describe and stop)

## Definition of Done
- [x] tsc clean  [x] eslint clean  [x] tests  … (full checklist)

## Blast radius
Components/modules that consume what I changed, and why they are unaffected.

## Not done
Anything incomplete, with a `// TODO:` in code and a reason here.
```

---

## 8. When you are blocked — the required behaviour

Do **not** guess. Do **not** stub silently. Do **not** widen scope to route around it.

Stop, and report in this shape:

```
BLOCKED: REQ-106 (Lead Priority scoring)
Reason: scoring weights for source / value / response time / engagement are undefined.
Docs checked: Requirements.md REQ-106, Open-Questions.md Q14, Decisions.md — no ADR.
Needed to proceed: the weight of each factor and the Hot/Warm/Cold thresholds.
Work completed anyway: score storage column, UI badge component, tests against a mock scorer.
```

Partial progress on the unblocked parts is expected. Fabricated business rules are not.

---

## 9. Things that will get a PR rejected immediately

- `any`, `as unknown as`, `@ts-ignore`, `eslint-disable` without justification
- A frozen file modified
- A business rule invented without a Docs citation
- Authorization enforced only in the UI
- A mutation with no audit trail
- Hard-coded user-facing English strings
- A raw `<img>`, an inline `style={{}}`, a `<div onClick>`
- `useEffect` fetching data
- Console logs left in, commented-out code left in, unused imports left in
- A screen with no empty or error state
- "Improvements" outside the assigned REQ-ID
- **Writing the tests for your own feature** (§2 adversarial pairing)
- **Writing a test by reading the implementation** instead of the acceptance criteria
- An acceptance criterion with no corresponding test
- A test weakened, skipped or `.only`-ed to make CI pass

---

## 10. Context files — read before starting any task

| File | Read it for |
|---|---|
| [Requirements.md](Docs/Requirements.md) | your REQ-ID, its tier, its dependencies |
| [Acceptance-Criteria.md](Docs/Acceptance-Criteria.md) | **the exact behaviour you must produce, and that tests will assert** |
| [Testing.md](Docs/Testing.md) | what "tested" means here — the gate you must clear |
| [Architecture.md](Docs/Architecture.md) | where your code goes and what it may talk to |
| [Decisions.md](Docs/Decisions.md) | why the stack is what it is — do not relitigate |
| [Documentation.md](Docs/Documentation.md) | how existing modules already solve your problem |
| [Open-Questions.md](Docs/Open-Questions.md) | whether your business rule is already known to be undefined |
| [Issues.md](Docs/Issues.md) | known problems in the BRD and the build that may affect your task |
| `Docs/RBAC.md` *(pending)* | the exact permission matrix |
| `Docs/Glossary.md` *(pending)* | what "dealer", "taluka", "depot", "MOM", "agent" mean here |

**Reuse before you write.** The reference vertical slice (Leads) is the pattern for every module. The data table, form primitives, audit hook, timeline emitter and permission guard already exist — find them and use them. Introducing a second way to do something already solved is a review rejection.
