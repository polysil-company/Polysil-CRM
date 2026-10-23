# Documentation — Living Product & Technical Reference

> **Status:** SKELETON — populated as modules ship. This is not written up-front; it is written by whichever model completes a `REQ-ID`, as part of its Definition of Done.

This is the file a new contributor (human or model) reads to answer *"how does this system actually work, and has someone already solved my problem?"* It is deliberately different from [Architecture.md](Docs/Architecture.md), which describes intent. **This file describes what exists.**

---

## How to use this file

- **Before writing code:** search here for your module and its neighbours. If a helper, hook, or service already exists, use it. Introducing a second way to do a solved problem is a review rejection ([AGENTS.md §10](Docs/AGENTS.md)).
- **After completing a REQ-ID:** append or update the module entry using the template in §5. A PR without a Documentation.md update does not satisfy the Definition of Done.
- Keep entries **short and factual**. Rationale belongs in [Decisions.md](Docs/Decisions.md), not here.

---

## 1. Quick orientation

| I want to… | Go to |
|---|---|
| Understand what we agreed to build | [Requirements.md](Docs/Requirements.md) |
| Understand why the stack is what it is | [Decisions.md](Docs/Decisions.md) |
| Know the rules before I write code | [AGENTS.md](Docs/AGENTS.md) |
| Find an unanswered business rule | [Open-Questions.md](Docs/Open-Questions.md) |
| Understand the system shape | [Architecture.md](Docs/Architecture.md) |
| Learn a concept used here | [Learning.md](Docs/Learning.md) |

---

## 2. Getting started *(to be filled Week 1 D5)*

```
# prerequisites, install, env setup, local Supabase, seed, run, test
# TODO: written once the repo is scaffolded
```

| Item | Value |
|---|---|
| Node version | _TBD_ |
| Package manager | _TBD_ |
| Local DB | _TBD_ |
| Seed command | _TBD_ |
| Test commands | _TBD_ |
| Staging URL | _TBD_ |

---

## 3. Cross-cutting systems *(the things every module touches — filled Week 1)*

These are documented first because every feature module depends on them.

| System | Where | What it does | Status |
|---|---|---|---|
| Auth & session | `src/lib/auth` | Resolves user, role, org unit, channel partner | ⬜ not built |
| Permission guard | `src/lib/rbac.ts` | `can(actor, module, action)` — mirrors the RLS policy | ⬜ |
| Hierarchy scoping | `src/lib/hierarchy.ts` | Closure-table lookups; who-can-see-whom | ⬜ |
| Audit trail | DB trigger + `audit.service.ts` | Append-only change log, old → new | ⬜ |
| Activity/timeline bus | `activity.service.ts` | Every module emits here; powers the 360° view | ⬜ |
| Approval engine | `approval.service.ts` | Generic request → route → decide → audit | ⬜ |
| Notification engine | `notification.service.ts` | Fan-out to in-app / email / WhatsApp / SMS | ⬜ |
| GST engine | `gst.service.ts` | Per-line CGST/SGST/IGST, rounding, HSN | ⬜ |
| Data table | `components/data-table` | The one grid: filter, sort, page, export, URL state | ⬜ |
| Form primitives | `components/ui/form` | RHF + Zod + error/disabled/loading states | ⬜ |
| i18n | `src/messages` | en / hi / gu key files | ⬜ |

---

## 4. Module index *(one row per shipped module)*

| Module | REQ-IDs | Owner model | Status | Entry below |
|---|---|---|---|---|
| _none yet_ | | | | |

---

## 5. Module entry template

Copy this block for each completed module. Keep it tight — this is a map, not an essay.

```markdown
### <Module name>

**REQ-IDs:** REQ-xxx, REQ-yyy
**Built by:** <model> · **Reviewed by:** Nakul · **Shipped:** YYYY-MM-DD

**What it does** — two sentences, in business language.

**Routes**
| Path | Audience | Purpose |
|---|---|---|

**Data**
| Table | Purpose | Notable columns / indexes |
|---|---|---|

**RLS** — who can see and do what, one line per role.

**Services** — exported functions and their one-line contracts.

**Business rules implemented** — each with its Docs citation. Rules deliberately NOT implemented are listed with the blocking question.

**Events emitted** — what this module writes to the activity timeline.

**Integrations touched** — WhatsApp / SMS / email / cron.

**Edge cases handled** — the non-obvious ones a future contributor would otherwise re-discover.

**Known gaps / TODOs** — with REQ or question references.
```

---

## 6. Operational reference *(filled before go-live, Week 5)*

| Topic | Status |
|---|---|
| Environment variables and where each is set | ⬜ |
| Deploy and rollback procedure | ⬜ |
| Database backup / PITR / restore drill | ⬜ |
| Cron job inventory and what breaks if each fails | ⬜ |
| WhatsApp template inventory and re-approval process | ⬜ |
| Common support tasks (reset a dealer login, re-send an OTP, correct a ledger entry) | ⬜ |
| On-call and escalation for the 30-day support window | ⬜ |

---

## 7. Glossary pointer

Domain terms — *taluka*, *depot*, *sub-dealer*, *agent*, *MOM*, *subsidy*, *scheme*, *institutional sale* — are defined in `Docs/Glossary.md` *(to be created Week 1 D1)*. Four models each inventing their own meaning for "dealer" is a real failure mode; the glossary exists to prevent it.
