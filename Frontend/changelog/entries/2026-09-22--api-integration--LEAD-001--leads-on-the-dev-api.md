---
date: 2026-09-22
type: api-integration
title: Leads run on the backend's dev API — list, lead page and New lead form, with real lookups
dataIds:
  - LEAD-001
  - LEAD-002
  - LEAD-003
  - LEAD-004
  - MSTR-002
  - OBS-002
  - APP-004
  - AUTH-004
  - DS-001
author: Nakul Srivastava
breaking: true
---

## Before

The app ran on the mock backend or on a backend started on the same machine — all or nothing. The backend team's shared dev API (`https://polysil-api.pranayx.tech`, real data, 20 staff accounts and a dealer) had no way in: turning mocks off would also have turned off the dashboard, notifications and messages, which it does not serve yet.

Leads ran on a contract the frontend had guessed: page numbers, a `/leads/summary` count, six fixed sources, seven stages, money as numbers, district and state typed by hand. None of it matched the backend that now exists.

## Now

**Local development against the dev API (OBS-002, APP-004, AUTH-004)**

- **A third mocking mode, `partial`.** `NEXT_PUBLIC_API_MOCKING=partial` mocks only what the backend does not serve yet — dashboard figures, notifications and messages — and sends everything else to `API_PROXY_TARGET`: sign-in, the session, sign-out, leads and the lookups. Like `enabled`, it is refused in staging and production builds.
- **One list of what is still mocked:** `unbuiltHandlers` in `src/mocks/handlers/index.ts`, each with a `TODO(DATA-ID)`. Connecting a module means taking it out of that list — leads and lookups are out.
- **The account menu** keeps the data scenarios in `partial` mode and drops "Preview as role", because the real session decides the role. The sidebar card reads "Dev API + mocks".

**The leads list (LEAD-001)**

- Pages with the backend's page tokens. The tokens of the pages already passed sit in the URL (`?cursors=…`), so a refresh, a bookmark or a shared link lands on the same page; "Previous" steps back through them. Changing a filter, the sort or the page size returns to the first page.
- The caption reads "1–25 of 74" from the backend's count. When the backend stops counting at 1,000 it says so, and the caption reads "1–25 of 1,000+" with "Page 3" instead of a page count that would be wrong. The table then tells assistive tech its row count is unknown.
- Filters: **Stage** (several at once; with none chosen the backend leaves out merged leads), **Source** and **Type** (one at a time, as the backend filters — these two pills are now single-choice radios). Source options come from the administrators' list, with a "Loading sources…" or error line until they arrive. Search matches the farmer's name, part of the mobile number, or the exact inquiry number.
- Columns stay as they were. Stage shows the backend's nine stages (merged and dormant are new); Source shows the list's name ("Agri Fair"); Owner shows "Unassigned" for leads waiting in a manager's list; Value reads the backend's decimal strings. Crops, Probability, Activity and Follow-up show "—" until the backend records them.
- The sort arrows on Customer and Value send `sort` and `order`. The backend lists newest first and does not sort yet — asked (Frontend-Scope §10). The mock backend sorts, so the behaviour can be previewed.
- New states: a page link the backend no longer accepts ("This page link no longer works", with a way back to the first page); a later page that has emptied since the link was made. Clicking "Next" twice while a page loads no longer skips a page.
- The selection bar adds the selected leads' values exactly, in whole paise.

**The lead count (LEAD-004)** — the sidebar badge and the Sales tab ask `GET /leads` for one row and the count, and show "1,000+" when it is capped. The tab no longer asks when the user cannot see leads.

**The lead page (LEAD-003)** — the real record: stage and priority badges; mobile, email, territory with its level, village, irrigation system, estimated value, owner and office (or "Unassigned · office"), channel partner and type, score, first contact, last activity, created on and by, times reopened, and for a lost lead its reason and note. A merged lead points to the lead it was merged into; possible duplicates are listed with how they matched ("same mobile number"). Land, crops, follow-up, win probability and engagement show "—".

**The New lead form (LEAD-002)**

- Fields match the backend: farmer name, mobile, email (optional), **territory** — a searchable picker that lists districts when opened and finds any taluka or village as you type, naming the place above each ("Gondal · Taluka in Rajkot") — village (optional), inquiry type, irrigation system (from the administrators' list), source (optional; left empty, the backend records who entered it), estimated value (optional) and a note that becomes the first timeline entry.
- Lists that fail to load say so, with "Try again" beside the field. The picker shows "Loading districts…", "Searching…", "No place matches" and a connection message.
- Saving retries safely: the same details reuse the same idempotency key, so a save whose reply was lost is replayed by the backend instead of creating the lead twice. Changing any detail makes a new key.
- A duplicate is never refused — the backend flags it, and the success message says "Possible duplicate of POL/… (same mobile number) — flagged for review".
- Field errors from the backend land on their field. A territory no office covers reads "No Polysil office covers this place yet. Choose the taluka or district around it." instead of the backend's developer wording.

**Design system (DS-001)** — two restyled primitives, each with a story: **Combobox** (a Select you type into, for long lists) and **RadioGroup**. **SingleFilterPill** joins FilterPill for filters that take one value. Touch targets are 44px on touch screens; both themes use existing tokens only.

## Discussion

- **Decided with Nakul (2026-09-21):** keep today's columns and show "—" where the backend has no data; keep the sort arrows and ask the backend for sorting; connect list, detail and the New lead form in one go, with the real lookups; keep working in `Loopify\Polysil-CRM`.
- **Page tokens in the URL, not page numbers.** The backend pages by keyset cursor and never jumps to page N. Keeping the trail of tokens in the URL is what makes "page 3" survive a refresh and be shareable; the alternative, tokens in memory, loses the page on reload. Tokens are base64url, so they never contain the list's comma separator.
- **Breaking:** the lead contract (`Lead` now carries `stage`, `territory`, `misSystem`, decimal-string money and more), the URL parameters (`status` → `stage`; `page` → `cursors`; `source` and `type` take one value), and `LeadStatusBadge` → `LeadStageBadge`. Old links with `?status=` or `?page=` simply open the unfiltered first page. `readFieldErrors` moved from the sign-in feature to `lib/api/errors.ts` for everyone.
- **Money is a decimal string end to end.** Formatters accept it as it is; totals are added in whole paise with `sumRupees`, never with floating point (0.10 + 0.20 is 0.30, not 0.30000000000000004). Unreadable amounts show "—" and count as zero in a total rather than failing it.
- **Lookups (MSTR-002)** are fetched once and shared by every cell, filter and form (ten minutes fresh). A code shows in readable form ("farmer_meeting" → "Farmer meeting") until its name arrives. The form offers active rows only; filters keep inactive ones, because old leads still carry them.
- **Partial mode's one seam:** messages are still mocked but leads are real. The mock now accepts a real lead linked in a message and names it "Lead", instead of refusing every real lead.
- **Mocks follow the backend:** seeded sources, irrigation systems and lost reasons from its migrations; the territory tree and partners shaped like its showcase seed; its search rules, default stage filter, 1,000 ceiling, cursor refusal, idempotency replay and 409, duplicate flagging, and `territory_without_org_unit` (Dang has no office in the mock, to preview it). The dashboard mock assumes a follow-up three days after the last activity, since the backend records none.
- **Asked of the backend** (Frontend-Scope §10, questions 14–18): sorting; a follow-up date; crops and acreage; win probability and weekly activity (or confirmation that the score and timeline replace them); which territory levels a lead may sit in.
- **Not done:** honouring `must_change_password` (AUTH-002); the lead timeline, stage changes, assignment and merging (their endpoints exist); integration on staging.

## Files changed

- `src/lib/env/client.ts` — `partial` mode, refused in staging and production
- `src/mocks/handlers/index.ts`, `src/mocks/browser.ts` — the still-mocked list; leads and lookups leave it
- `src/components/providers/mock-gate.tsx`, `src/components/layout/user-menu.tsx`, `src/lib/dev/mock-settings.ts` — mock controls by mode
- `src/components/layout/app-sidebar.tsx` — environment card by mode; lead count from `GET /leads`, "1,000+" when capped
- `src/features/leads/api/` — the backend's lead contract, list, detail, count and create with a reusable idempotency key
- `src/features/leads/hooks/use-lead-list-params.ts` — URL state: page tokens, stage, single source and type
- `src/features/leads/components/` — table (tokens, capped total, stale links), toolbar (single-choice pills, lookup sources), columns, lead page, New lead form, sales tab; `lead-status-badge.tsx` → `lead-stage-badge.tsx`
- `src/features/leads/lib/lead-labels.ts`, `create-lead-errors.ts`, `lead-table-layout.ts` — nine stages, priorities, partner types, duplicate wording; 422 field mapping
- `src/features/lookups/` — new: lookup lists and territory search (MSTR-002), `LookupName`, `LookupSelect`, `TerritoryPicker`
- `src/components/ui/combobox.tsx`, `radio-group.tsx` (with stories) — new primitives
- `src/components/patterns/filter-pill.tsx` (+ story), `data-table/data-table.tsx`, `nav-tabs.tsx` — single-choice pill; capped and unknown totals, cursor paging; capped tab counts
- `src/lib/api/pagination.ts`, `src/lib/api/errors.ts` — the backend's page metadata; `readFieldErrors` shared
- `src/lib/format/currency.ts`, `number.ts`, `index.ts` — decimal-string money, `sumRupees`, `formatCount`
- `src/hooks/use-debounced-value.ts` — search as you type
- `src/features/auth/` — imports `readFieldErrors` from its new home
- `src/features/dashboard/` — stage labels and source names (mocked contract, RPT-001)
- `src/mocks/` — leads, lookups and territories in the backend's format; lead, lookup, dashboard and message handlers
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — LEAD-001…004 in progress on the dev API, LEAD-004 re-described, MSTR-002 registered
- `Docs/Environments.md`, `Docs/Frontend-Scope.md`, `Docs/Design-System.md`, `.env.example` — the dev API, what leads cannot show yet, questions for the backend, new components
- `eslint.config.mjs` — `RadioGroupItem` counts as a labelled control
- `src/test/render.tsx` — tests can follow URL changes
- `vitest.config.mts`, `playwright.config.ts` — tests pin the full mock backend, whatever `.env.local` says

## Tests

- `src/features/leads/api/leads.test.ts` — `[LEAD-001]` first page and total, parameters sent, cursor paging to the last page, stages (merged only when asked), source and type, search by inquiry number and mobile, capped total, refused cursor; `[LEAD-003]` shape and duplicates, 404; `[LEAD-004]` count and capped count; `[LEAD-002]` create, duplicate flagged, retry replayed, key reused → 409, uncovered territory on its field; form schema; 422 field mapping
- `src/features/leads/components/leads-ui.test.tsx` — `[LEAD-001]` skeleton → rows and total, source names, next and previous page with the URL, "1,000+", emptied later page, stale link, empty and filtered-empty, server error, contract violation; `[LEAD-002]` every required field explained
- `src/features/lookups/` — `[MSTR-002]` lookup lists, inactive rows, territory search, labels, `TerritoryPicker` (districts on open, search and choose, nothing matches)
- `src/components/patterns/filter-pill.test.tsx`, `data-table/data-table.test.tsx` — single-choice pill; range, capped total, cursor-decided next page
- `src/lib/format/format.test.ts`, `src/lib/api/pagination.test.ts`, `url-and-errors.test.ts`, `src/hooks/use-debounced-value.test.ts`, `src/mocks/data/leads.test.ts`, `src/mocks/handlers/index.test.ts`, `src/lib/env/client.test.ts` — money strings and paise totals, page metadata, field errors, debounce, mock data against the contract, the mocked list, `partial` mode
- By hand, with `.env.local` pointing at the dev API: sign in as `admin@`, `asha@` and `ravi@polysil.in` — the caption shows each one's own total (74, 34, 23); page forward, refresh, and land on the same page; filter by stage, source and type; open a lead; create one with a taluka from the picker; create another with the same mobile and see the duplicate warning. Check at 360px and on a wide screen, in light and dark.
