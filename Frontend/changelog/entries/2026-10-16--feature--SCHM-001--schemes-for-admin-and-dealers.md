---
date: 2026-10-16
type: feature
title: Schemes for Admin and dealers
dataIds:
  - SCHM-001
  - SCHM-002
  - SCHM-003
  - SCHM-004
author: Nakul Srivastava
breaking: false
---

## Before

The backend runs promotional schemes for dealers (handover `schemes-contract.md`, FS-031). There are four types: an order discount, points on an order, a credit for the next order, and a monthly or quarterly target. Admin defines them, and dealers see theirs, their standing and their credits. "Schemes" sat in the menu marked Soon.

## Now

- **Channel → Schemes** (`/schemes`), with a **Credits** tab.
- **The list** (SCHM-001) is newest first. Each scheme shows:
  - what it gives and who qualifies, in words ("5% off, up to ₹50,000 · Orders of ₹2,00,000 or more");
  - its dates;
  - whether it's running, scheduled, ended or switched off.
- **Filters:** staff filter by status, type and a search. A dealer sees only the running schemes aimed at it.
- **A scheme's page** shows its terms. Staff also see who it's for: a line per kind of target, where any one name on a line will do and every line must match. A dealer never sees who else a scheme is for.
- **New scheme and Edit** (SCHM-002, for administrators):
  - **The type decides what's asked.** It sets the benefits offered (a points scheme gives points, and points have no cap), whether a credit's life is asked (next-order credits, and a period's credit), and whether the period is a month or a quarter.
  - **Who it's for** adds territories (the territory picker), partner types, partners and products. Nothing added means everyone.
  - **Checks before sending** mirror the backend's rules, each named on its field: a percentage over 100, points that aren't whole, a maximum under the minimum, a period scheme without an end date.
  - **The backend's refusals** land on their fields. A taken code says so.
  - **Edit** sends only what changed.
- **A scheme that has given benefits** keeps its terms. The page and the form say why, and only an earlier end date can be set.
- **Switch off and Switch on** sit on the scheme's page. Switching off stops new benefits, and credits already earned stay usable.
- **Standing** (SCHM-003), on a period scheme, shows what has been delivered so far this month or quarter against the target, with a bar and what's left to go. A dealer sees its own; staff pick a partner.
- **Credits** (SCHM-004) show each credit with:
  - its value, its scheme and its status;
  - when it was earned, and on which order or for which period;
  - when it must be used by, and the order it was used on.
    A dealer sees its available credits first. Staff see every partner's and may narrow the list to one.
- Checked on a phone in dark mode and a desktop in light mode, as Admin and as a dealer. axe found nothing.

## Discussion

- **Target names (BE-027).** The backend answers a scheme's targets as `{ type, id }`. Until it sends names, each one is read from its own record (`/territories/{id}`, `/partners/{id}`, `/products/{id}`), and the frontend reads `name` as soon as it comes. A reader who can't open the record sees the kind and a short id.
- **Product categories can't be added yet.** A category target takes an id, and nothing lists category ids (BE-024 lists codes). BE-027 asks for both.
- **Contract details from the backend's code:**
  - `used` and `is_current` on a scheme;
  - which benefit kinds each type takes;
  - the 90-day default for a credit's life;
  - `targets[i].id` field errors;
  - `scheme_in_use` for anything but an earlier end date on a used scheme.
- **Benefits on an order are a second pull request (item 24b).** That covers the preview on a draft and the benefits and "To pay" after submit. It touches `payable` on the order, which PRs #142 and #144 add, so it stacks on them.
- **The mock** seeds six schemes and four credits. A dealer sees the schemes aimed at its type or itself; every mock partner is in Gujarat, so a territory target always matches. Standing is drawn from the partner's id, because the mock keeps no deliveries. The mock also serves `GET /territories/{id}` to name territory targets.

## Files changed

- `src/features/schemes/` — new:
  - the contract, calls, queries and mutations;
  - the scheme labels;
  - the list, a scheme, the form with its targets editor and record pickers, the credits list and the tabs, with tests.
- `src/app/(app)/schemes/` — new: the layout, the list, `new`, `[schemeId]`, `[schemeId]/edit` and `credits`.
- `src/components/layout/navigation.ts` — Schemes opens `/schemes`.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — SCHM-001 filled in; SCHM-002 to SCHM-004.
- `src/mocks/data/schemes.ts` (new), `src/mocks/handlers/schemes.ts` (new), `src/mocks/db.ts`, `handlers/index.ts` — the seeds and the endpoints with the backend's rules.
- `../docs/Backend-Tasks.md` — BE-027.
- `Docs/Plan.md`, `Docs/Tested-Features.md`, `Docs/screenshots/schemes/` — records and screens.

## Tests

- `src/features/schemes/components/schemes.test.tsx`:
  - `[SCHM-001]` through the API: every scheme for staff; a dealer's running schemes without partner targets.
  - `[SCHM-002]` through the API:
    - create;
    - a taken code;
    - a period scheme with no period or end date;
    - a State Manager refused;
    - a used scheme refusing a new name, but taking an earlier end and the switch.
  - `[SCHM-003]` a dealer's standing; another type refused; staff without a partner refused.
  - `[SCHM-004]` a dealer's own credits; staff see all.
  - The list for Admin and for a dealer.
  - The form:
    - what's missing named;
    - only the benefits a type takes;
    - creating;
    - a used scheme's end date.
  - A scheme: its terms, its targets named, Switch off.
  - A dealer's standing on a period scheme, and a dealer's credits.
- Walked through in the mock:
  - as Admin, on a desktop: the list, a new scheme (first empty, then filled and created), a used scheme and its form, a period scheme's standing for a partner, and the credits;
  - as a dealer, on a phone in dark mode: the list, the standing and the credits.
