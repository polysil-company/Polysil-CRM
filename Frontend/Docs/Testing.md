# Testing Strategy

**This project is gated by tests, not by code review.** That is a deliberate decision ([ADR-016](Docs/Decisions.md)), and it only works if the testing is genuinely rigorous. This document is what "rigorous" means here.

The premise: what matters to the client is that **functionality is correct and the application does not break under real scenarios**. Line-by-line review of implementation code does not reliably deliver that — it catches style and structure, and misses behaviour under edge conditions. Executable tests do the opposite. So we spend the effort there.

---

## 1. What is still reviewed by a human

Dropping review entirely would be a mistake, because two failure classes are structurally invisible to functional tests (see [ISS-013](Docs/Issues.md)). So the review surface is not zero — it is **narrowed to where tests cannot reach**:

| Reviewed by Nakul / Opus 5 | Not reviewed — gated by tests |
|---|---|
| `supabase/migrations/**` — the data model | Feature components |
| `src/contracts/**` — Zod schemas | Screens, forms, tables |
| Service **signatures** | Service bodies |
| `rbac.ts`, `hierarchy.ts` | Report rendering |
| RLS policies | Integration adapters |
| `Docs/RBAC.md` matrix | Everything else |

That is roughly **2–3k lines instead of 130k**. A wrong table relationship or a leaky RLS policy passes every functional test and costs a rebuild in month three; a wrong button label does not. Effort goes where the blast radius is.

---

## 2. The testing pyramid for this project

| Layer | Tool | What it covers | Volume |
|---|---|---|---|
| **Business logic** | Vitest | GST, lead scoring, dedupe, ledger arithmetic, SLA computation, hierarchy resolution, scheme applicability | Exhaustive — this is where money and law live |
| **Authorization** | Vitest + real Postgres | Every role × table × operation, **including negative cases** | Generated from the RBAC matrix |
| **Contract** | Vitest | Zod schemas accept valid and reject invalid payloads; webhook payloads from real captured samples | Per contract |
| **Service integration** | Vitest + test DB | Service functions against a real seeded database, transactions, audit-trigger firing | Per service |
| **End-to-end** | Playwright | Named critical user journeys, per role, on real UI | ~20 flows |
| **Scenario / resilience** | Playwright + fixtures | The "application shouldn't break" cases — see §5 | ~30 scenarios |
| **Performance** | Playwright + `scale` seed | Report and timeline queries at 500k+ rows | Per report |
| **Accessibility** | axe-core in Playwright | WCAG 2.2 AA on every route | Automatic |
| **Visual** | Playwright screenshots | Layout regression at 360px / 768px / 1440px | Per screen |

---

## 3. Acceptance criteria come first — this is the load-bearing rule

**Tests are written from the requirement, never from the code.**

Every `REQ-ID` gets Given/When/Then acceptance criteria in [Acceptance-Criteria.md](Docs/Acceptance-Criteria.md) **before implementation begins**. Those criteria are the test specification. The implementing model receives the criteria; the testing model writes tests from the same criteria independently.

This is what prevents the central failure mode of AI-tested AI code ([ISS-012](Docs/Issues.md)): if one model both implements and tests, a misunderstood requirement produces a wrong implementation *and* a test that confirms the wrong behaviour. The suite goes green and nothing was verified.

Three defences, all mandatory:

1. **Criteria derive from `Docs/`, not from the code.** If a test needs a rule not written in the requirement, that is a BLOCKED report, not an inference.
2. **A different model writes the tests than writes the feature.** Enforced by the routing table in [AGENTS.md](Docs/AGENTS.md) §2.
3. **Mutation testing** (Stryker) on the business-logic core. It deliberately breaks the code and checks the tests notice. A test suite that passes against mutated code is not a test suite. Target: >85% mutation score on `services/` business logic. This is the only honest way to know that AI-written tests are testing anything.

---

## 4. Authorization testing — generated, not written

Hand-written permission tests cover what someone remembered. With 9 CRM roles + 5 portal roles across ~25 tables and 4 operations, that is ~1,400 combinations. Nobody writes those by hand, and nobody writes the *negative* ones — which are the ones that matter.

So they are **generated from `Docs/RBAC.md`**. The matrix is the single source of truth; a script emits the full test matrix; CI asserts every cell, both allow and deny. Adding a role or a table regenerates the suite automatically.

Each cell asserts three things:
- the permitted action succeeds
- the forbidden action **fails at the database layer**, not merely at the UI
- the attempt is recorded where it should be

Plus explicit hierarchy tests: a Sales Manager in Rajkot cannot see a Surat manager's leads; a sub-dealer cannot see its parent dealer's ledger; a dealer cannot see a sibling dealer's anything.

---

## 5. Scenario testing — "the application shouldn't break"

This is the category the client actually cares about, and it is the one most commonly skipped. Every module ships with scenario coverage from this checklist:

**Data-shape scenarios**
- Empty state — zero leads, zero orders, brand-new dealer
- Single record, exactly-one-page, exactly-page-boundary (10, 11, 100, 101 rows)
- Very large values — a ₹4,00,00,000 order, a 200-line quotation
- Unicode — Gujarati and Hindi names, in forms, in exports, in PDFs, in WhatsApp templates
- Long strings — a 300-character dealer name that must not break layout
- Nulls in every optional field, simultaneously

**Lifecycle scenarios**
- Every state transition in the quotation, order, complaint and approval state machines — *including the illegal ones, which must be rejected*
- Actions on an expired scheme, a cancelled order, a closed complaint, a deactivated dealer
- A record edited by two users at once (concurrency / lost update)
- A record whose owner has been deactivated or reassigned mid-flow

**Permission scenarios**
- Every screen loaded by every role that shouldn't have it
- A user demoted mid-session
- A dealer whose parent distributor is reparented while they are logged in
- Direct URL access to another partner's record ID

**Integration-failure scenarios**
- WhatsApp API down, rate-limited, returning a template-rejected error
- SMS provider timing out mid-OTP
- Webhook delivered twice (idempotency), delivered out of order, delivered with a bad signature
- Payment/ledger write succeeding while notification fails — must not roll back the money
- File upload interrupted, oversized, wrong MIME type

**Environment scenarios**
- 3G throttled connection on the dealer portal
- Session expiry mid-form — the user's typed data must not vanish
- Two tabs open, conflicting actions
- Browser back button after a submit
- 360px viewport for every screen, since that is the real dealer device

**Money scenarios** *(these get their own attention because errors here are legal)*
- Intra-state vs inter-state GST on the same product
- Rounding at the paisa boundary, per line and on the total
- Scheme discount + tier price + GST applied in the correct order
- Partial payment, overpayment, subsidy portion pending, refund after part-settlement
- Currency formatting in the Indian numbering system (₹1,00,000 not ₹100,000)

---

## 6. CI gates

Every PR. Merge is blocked unless all pass.

```
1. tsc --noEmit                      zero errors
2. eslint .                          zero warnings
3. vitest run                        all green, including generated RBAC matrix
4. playwright test --grep @critical  critical journeys green
5. axe accessibility                 zero serious/critical violations
6. build                             succeeds
```

Nightly, on `main`:

```
7. playwright test                   full suite including scenarios
8. stryker run                       mutation score >85% on services/
9. performance suite                 p95 < 2s on every report at scale seed
10. visual regression                no unapproved diffs
11. load test @ 300 concurrent     API p95 < 400ms, zero connection errors
```

A red nightly on `main` stops new feature merges until it is green. That rule is what keeps a test suite from quietly rotting into decoration.

---

## 7. Test data

Two seed profiles, both committed:

| Profile | Contents | Used for |
|---|---|---|
| `demo` | Realistic Gujarat data — real taluka names, plausible dealer names, actual SKU patterns, believable order history | Client demos, UAT, manual testing |
| `scale` | 500k+ activity events, 3k partners, 50k customers, 5 years of orders | Performance assertions in CI |

### Load testing - new, and not optional

Confirmed load is 700-800 named users with 100+ concurrent, and a seasonal profile that will exceed that ([ISS-017](Docs/Issues.md)). Two failure modes are **structurally invisible** to every test above: Postgres connection exhaustion under serverless fan-out, and RLS policies whose per-row cost is negligible at 50 rows and fatal at 500k ([ISS-018](Docs/Issues.md)).

Both produce a system that is green in CI, flawless in the demo, and down on the first busy morning. So they get their own gate:

| What | Tool | Target | When |
|---|---|---|---|
| Sustained load | k6 against the `scale` seed | **300 concurrent** virtual users, API p95 < 400ms, **zero** connection errors | Nightly |
| RLS policy cost | `EXPLAIN ANALYZE` assertions per policy at scale volume | no per-row subplan; policy adds < 20% to query time | Per PR touching policies |
| Report p95 | performance suite | < 2s per report at scale seed | Nightly |
| Mobile sync burst | simulated queue flush | 100 devices, no duplicates, no timeouts | Nightly |

The 300-concurrent figure is deliberate. Sizing to the stated average of 100 means the system meets its real test during a subsidy deadline - which is exactly when it must not fail.

Never "Test Dealer 1". A client demo on fake-looking data undermines confidence in real work, and scale problems that only appear at volume must appear in CI rather than in production.

---

## 8. Manual testing — where it still earns its place

Automation does not cover everything. These stay manual, on a checklist, before each weekly demo:

- Real WhatsApp messages received on a real phone, in Gujarati, rendering correctly
- The quotation PDF opened in Gmail on Android, WhatsApp preview, and print
- The field app on an actual low-end Android device, outdoors, with real GPS drift
- Gujarati typography at 360px — line height, truncation, form labels
- The full dealer onboarding journey, performed by someone who has not seen the app
- Exported Excel opened in the client's actual Excel version

---

## 9. Who writes what

| Test type | Author |
|---|---|
| Acceptance criteria | Opus 5 + Nakul, from the requirement, before build |
| Business-logic unit tests | The model *not* implementing that logic |
| RBAC matrix tests | Generated from `Docs/RBAC.md` |
| E2E critical flows | Sonnet 5 or GPT 5.6 Sol — never the model that built the feature |
| Scenario suites | GPT 5.6 Luna (integration failure), Sonnet 5 (data/lifecycle) |
| Performance | GPT 5.6 Sol |
| Manual checklist | Nakul |

---

## 10. What we deliberately do not do

- **Chase a coverage percentage.** 100% line coverage on CRUD boilerplate proves nothing. We cover where bugs cost money, access, or legal standing.
- **Snapshot-test component markup.** It breaks on every refactor and catches nothing real.
- **Mock the database in service tests.** Services run against real Postgres with real RLS, because RLS behaviour *is* the thing under test.
