# Learning Log

Two purposes:

1. **Concepts** — anything used in this project that is worth understanding from first principles rather than copy-pasting. Written plainly, no hand-waving.
2. **Retros** — what we got wrong each week, and what changed as a result. Honest entries only; a retro that lists no mistakes is a retro nobody wrote.

---

# Part 1 — Concepts

## C-01 · Row Level Security (RLS), and why authorization belongs in the database

**The problem.** Normally we check permissions in application code: `if (user.role !== 'manager') throw`. That works right up until something reaches the data another way — a cron job, a webhook handler, a report query, a support engineer running SQL, or an AI-written endpoint that simply forgot the check. Every one of those paths is a hole, and each new path is a new chance to forget.

**The idea.** Postgres can attach a rule to a *table* saying which rows a given database user is allowed to see or change. The rule is a SQL expression evaluated per row. Once enabled, it applies to **every** query — application, cron, webhook, psql. There is no path around it.

```sql
create policy "sales exec sees own leads"
on leads for select
using ( owner_id = auth.uid() );
```

**Why it matters here specifically.** The BRD requires that "no module is left with undefined or default access", plus a tamper-proof audit trail. With four AI models writing endpoints in parallel, application-layer checks *will* be forgotten somewhere. RLS makes the forgetting harmless: the query returns zero rows instead of leaking a competitor's dealer ledger.

**The cost.** Policies are SQL, so they are harder to unit test than TypeScript, and a slow policy makes every query slow. Hence [ADR-004](Docs/Decisions.md)'s closure table — so the policy is an index lookup rather than a tree walk — and hence a dedicated RLS test suite in Week 1.

**Mental model:** application checks are a *courtesy to the user* (don't show a button that will fail). RLS is the *actual security boundary*. They are not redundant; they do different jobs.

---

## C-02 · Closure tables — making "who reports to whom" fast

**The problem.** Our hierarchy is Depot → Distributor → Dealer → Sub Dealer → Agent, arbitrarily deep. A Regional Manager must see everything beneath them. The naive schema is `parent_id` on each row, and the naive query is a recursive CTE that walks the tree.

That is correct and unusably slow when it runs inside an RLS policy — because the policy is evaluated *per row*, so listing 500 dealers walks the tree 500 times.

**The idea.** Maintain a second table that stores every ancestor–descendant pair explicitly:

| ancestor_id | descendant_id | depth |
|---|---|---|
| depot-1 | depot-1 | 0 |
| depot-1 | distributor-7 | 1 |
| depot-1 | dealer-42 | 2 |
| distributor-7 | dealer-42 | 1 |

"Can user X see row Y?" becomes one indexed lookup: *does a row exist with `ancestor_id = X.partner_id` and `descendant_id = Y.partner_id`?* Constant time, regardless of depth.

**The trade.** Writes get more expensive. Adding a dealer inserts one row per ancestor. Reparenting a distributor rewrites its whole subtree. That is the right trade here — reads happen thousands of times a day, reparenting happens rarely.

**Alternatives and why not:** `ltree` path strings are fast to read but reparenting rewrites every descendant's path and prefix matching gets awkward with RLS. Nested sets are read-optimal but brutal to update. Closure tables are the balanced choice, and they are trivially explainable — which matters when four models must all get it right.

---

## C-03 · Contract-first development, and why it is the *only* way multiple AI models can share a repo

**The problem.** Ask four capable models to build ten modules and you get ten reasonable-but-different approaches: four validation styles, three error-handling conventions, two ways to check permissions. Each is defensible. Together they are unmaintainable, and the review burden explodes because every PR must be evaluated on *design* as well as correctness.

**The idea.** Freeze the interfaces *before* any feature work starts, then let parallelism happen only in the space below those interfaces.

```
Frozen first:  schema → Zod contracts → service signatures → UI primitives
Then parallel: feature implementation, which may only consume the above
```

Because the contracts are frozen, a model implementing quotations and a model implementing complaints cannot conflict — they are writing different files against the same fixed types. Review shifts from "is this design acceptable?" to "does this correctly implement a settled design?", which is dramatically faster and far more reliable.

**The discipline that makes it real:** a model that finds a frozen contract inadequate must *stop and report*, not work around it. A work-around is how a second architecture is born. This is [AGENTS.md §3](Docs/AGENTS.md), and it is the single most important rule in this project.

**Second-order benefit:** the frozen layer is also the *test* layer. Freeze the Zod schema and the GST service signature, and both can be exhaustively unit-tested before a single screen exists.

---

## C-04 · Indian GST in software — the parts that bite

Worth internalising because REQ-203 touches money and errors here are legal, not cosmetic.

- **Intra-state vs inter-state.** Same state (seller and buyer): tax splits into **CGST + SGST**, half each. Different states: a single **IGST** at the full rate. So the *buyer's state* changes the shape of the invoice, not just the number. Place of supply is determined by the delivery address.
- **HSN codes.** Every product carries an HSN code that determines its rate. It belongs on the SKU master (REQ-004) and must appear on the document.
- **Rounding.** Computed per line, then totalled — not computed on the total. Rupee rounding at the end, half-up. Getting the order wrong produces off-by-one-paisa mismatches that accountants *will* find.
- **Never use floating point for money.** `numeric(14,2)` in Postgres, integer paise or a decimal library in TypeScript. `0.1 + 0.2 !== 0.3` is a rounding curiosity in most software and an audit finding in this one.
- **Quotation ≠ invoice.** A quote is a commercial document with no statutory numbering requirement. A tax invoice has mandatory fields, an unbroken serial series, and above a turnover threshold, e-invoicing with an IRN from the government portal. **This is exactly why [Q12](Docs/Open-Questions.md) must be answered before Week 3** — the two are different products.

---

## C-05 · WhatsApp Business API — the constraints that shape the design

- **Templates.** You cannot send arbitrary text to someone who has not messaged you recently. Business-initiated messages must use a **pre-approved template** with fixed structure and variable placeholders. Approval takes 1–3 days *per template*. So the 12 templates must be drafted in Week 0, not Week 4.
- **The 24-hour session window.** Once a user messages you, you may reply freely for 24 hours. After that, templates only. This directly shapes REQ-604's inbox: an agent needs to *see* the remaining window, or they will write a reply that silently cannot be sent.
- **Opt-in.** Meta requires demonstrable consent, and DPDP Act 2023 requires it independently. Consent must be a stored record with a timestamp and source — not an assumption.
- **Pricing is per conversation**, not per message, and varies by category (marketing / utility / authentication / service). Automated reminders at scale have a real running cost the client should see modelled before launch.
- **Verification is the long pole.** Meta Business verification requires business documents and can take up to three weeks. Nothing about WhatsApp is buildable-to-production without it — which is why the module is built behind a mock provider ([ADR-009](Docs/Decisions.md)) so it is complete and demoable while verification is pending.

---

## C-06 · Why background location tracking cannot work in a PWA

REQ-702 asks for live location tracking and route history. This is worth understanding precisely, because it is the requirement most likely to cause a difficult client conversation.

- A web page only runs while it is open. `navigator.geolocation.watchPosition()` stops when the tab is backgrounded or the screen locks.
- **iOS Safari has no background geolocation for web apps at all.** Not a permission setting — the capability does not exist.
- Android is better but still aggressively throttles background web execution to protect battery.
- Continuous tracking requires an OS-level background service, which means a **native app** — React Native/Expo with a background-location module, plus Play Store and App Store declarations justifying the permission (both stores scrutinise background location heavily).

**Therefore:** Phase 1 delivers what the web genuinely can do well — check-in/check-out with GPS coordinates, timestamp and photo at each visit, which is what most field-sales workflows actually use. Continuous route history is an explicit Phase 2 native deliverable ([Q21](Docs/Open-Questions.md)). Saying this in Week 0 is a design constraint; discovering it in Week 5 is a broken promise.

---

## C-07 · DPDP Act 2023 — what it means for this build

India's Digital Personal Data Protection Act applies squarely here: we store farmer names, mobile numbers, addresses, payment records, and employee location traces.

Practical implications, none of them expensive if designed in from the start:

- **Consent must be recorded**, not assumed — with purpose, timestamp and source. This is why REQ-605 exists as its own requirement.
- **Purpose limitation** — data collected for order fulfilment is not automatically available for marketing blasts.
- **Data residency** is not strictly mandated, but hosting in `ap-south-1` removes the question entirely and is also faster for users in Gujarat.
- **Retention** — a stated policy, and a mechanism to honour it. Not a Week 5 bolt-on.
- **Employee location tracking** needs documented consent and an employment-policy basis. Tracking staff without it is the sharpest exposure in this BRD, and it sits in a requirement (REQ-702) that reads like a pure feature request.
- **Never log PII** — Sentry scrubbing configured before real data exists, not after the first incident.

---

# Part 2 — Weekly retros

Template:

```markdown
## Week N — <dates>

**Shipped:** REQ-IDs that reached DONE.
**Slipped:** what did not, and the real reason.
**What broke:** bugs that reached staging, and the class of mistake behind each.
**Model performance:** which routing worked, which did not.
**Review load:** PRs reviewed, average turnaround, whether the bottleneck was review.
**Client dependencies:** what moved, what is still 🔴.
**Changed as a result:** concrete process changes for next week.
```

---

## Week 0 — 2026-08-14

**Done:** BRD parsed into 73 traceable requirements. Docs foundation established. Independent 5-week plan drafted for comparison against Loopify's internal plan.

**Findings worth recording:**
- 33 of 73 requirements have undefined business rules. That is 45% of scope not yet buildable, and it is client-side work — no amount of engineering velocity moves it.
- 6 requirements are blocked on external verification processes (Meta, TRAI DLT) with lead times of 3–20 working days. These had to start on Day 1 and are the most likely cause of a Week 4 surprise.
- The BRD's biggest silence is what system currently owns stock, dispatch and ledgers ([Q9](Docs/Open-Questions.md)). The dealer portal is roughly a third of the scope and rests entirely on that answer.
- Two requirements (background location REQ-702, invoicing implications of REQ-203) contain expectations that are technically or legally different from how they read. Both surfaced now rather than later.

**Changed as a result:** contract-first sequencing adopted with hard frozen layers, because 45% undefined scope plus four parallel models is the exact condition under which guessed business rules get baked into production code.
