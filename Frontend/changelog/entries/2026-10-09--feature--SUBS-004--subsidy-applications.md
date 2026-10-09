---
date: 2026-10-09
type: feature
title: Subsidy applications
dataIds:
  - SUBS-004
  - SUBS-005
  - SUBS-006
  - SUBS-007
  - SUBS-008
author: Nakul Srivastava
breaking: false
---

## Before

The calculator (#77) could show what the scheme pays, but a subsidised sale couldn't go anywhere from there. The backend has served applications since FS-009 (`/subsidy-applications*`, `/subsidy-stages`; handover `subsidy-applications-contract.md`):

- starting one from a lead;
- the fourteen GGRC stages;
- the document checklist;
- the PIMS sheet;
- cancel.

None of it had a screen.

## Now

- **Subsidy has two tabs: Applications and Calculator.** The sidebar's Subsidy opens the worklist.
- **Starting from a lead.** A subsidised lead's page has a "Subsidy application" card.
  - It offers **Start subsidy application** when all of these hold: the lead is qualified, quoted, in negotiation or won; its system has a subsidy calculation; it has no live application; and the user may change applications. Otherwise the card says why.
  - The start page is the calculator for the lead's system. Then the farmer's category, listing only those that apply on every crop block, each with its subsidy. Then an optional survey number.
  - Starting moves the lead to won and opens the application at stage 4.
- **The worklist:**
  - each application's number, status, Reg. No., subsidy, farmer, stage and days in that stage;
  - filters on status, stage and a search, all in the URL;
  - Download Excel.
- **The application:**
  - its stage and ageing, the Reg. No. and documents;
  - the stored figures for the chosen category, and the farmer;
  - every stage entry, oldest first;
  - on request, the calculation as stored at the start.
  - **Record stage** builds its form from the scheme's stage list. It sends only the fields that changed, asks for a remark when going back or repeating a stage, and closes the application when the last payment date is in.
  - **Cancel**, with a reason.
  - **PIMS sheet**, a download.
  - View-only roles see everything but change nothing.
- **Documents:** the 20-item checklist, each item with its files.
  - Files go up against an item, each checked before it is sent and uploaded on its own.
  - Each is opened through a ten-minute link.
- On a phone, the figures come before the long checklist. Checked at 360 px in dark mode, with no sideways scroll.

- **Each lead's own scheme** (backend 044, handover `subsidy-schemes-contract.md`):
  - Starting asks `GET /subsidy-schemes/for-lead/{id}`. The calculator reads that scheme's systems, crops and categories, and the calculation is sent with its code.
  - A state with no scheme, or one not yet ready, says "Subsidy for this state is not set up yet".
  - `scheme_changed` reads the scheme again and says why.
  - Record stage reads the application's scheme's stages.
  - The PIMS sheet shows only on GGRC applications, the only scheme with one (GAP-363).

## Discussion

**Decisions:**

- **The stage form is data.** It is built from `GET /subsidy-stages`, never hard-coded, as the handover asks.
  - It starts from each field's latest value.
  - It sends only what changed, because an empty value clears a field on the backend. A field the user never touched can't be wiped.
- **Categories are filtered on the screen,** to those that apply on every crop block: the rule the backend enforces with `category_code`.
- **The stored calculation is shown, not recomputed.** It goes through the same figures component as the calculator, which was split out of the results panel for this (`CalculationFigures`).
- **`NavTabs` now picks the longest matching tab.** That keeps Applications (`/subsidy`) from lighting up on `/subsidy/calculator`. No existing tab set nests, so nothing else changes.
- **The lead's card.** `GET /subsidy-applications` can't filter by lead yet, so a new backend ask records it (**BE-023**). The frontend already sends `lead_id` and keeps only rows whose lead matches. Until the backend filters, an application beyond the first page could be missed.

**The mock:**

- Regional Managers and Accounts get subsidy as view-only, as the handover's table says.
- The mock follows the backend's rules: the starting refusals, the remark, the closing rule (every stage-16 amount with its stage-17 date), 409 once closed or cancelled, and the upload limits.
- Six applications are seeded from the subsidised won leads, at different stages, one of them cancelled.

## Files changed

- `src/features/subsidy/`:
  - `api/subsidy-applications.{schemas,api,queries,mutations}.ts`, with `subsidy-applications.test.ts`;
  - `lib/application-labels.ts` (statuses, who may start), `lib/stage-form.ts` (the stage form's values);
  - `components/`:
    - `applications-list.tsx`, `application-detail.tsx`, `application-actions.tsx` (record stage, cancel, PIMS);
    - `application-documents.tsx`, `start-application.tsx`, `lead-subsidy.tsx`, `subsidy-tabs.tsx`;
    - `applications-ui.test.tsx`;
  - `calculator-results.tsx`: `CalculationFigures`, split out; `subsidy-calculator.tsx`: `SystemCalculator` exported, with a slot under its figures.
- `src/app/(app)/subsidy/`: the layout with tabs, the worklist, `[applicationId]`, `new`; the calculator moves under the layout.
- `src/features/leads/components/lead-detail.tsx`: the lead's subsidy card.
- `src/components/patterns/nav-tabs.tsx`: the longest match wins.
- `src/components/layout/navigation.ts`: Subsidy opens `/subsidy`.
- `src/mocks/`: `handlers/subsidy-applications.ts`, `data/subsidy-applications.ts`; the database, id spaces and handler list; `handlers/subsidy.ts` exports its checks; view-only subsidy for Regional Managers and Accounts.
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md`: SUBS-004…008.
- `docs/Backend-Tasks.md`: BE-023.
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `Docs/screenshots/subsidy/`: the records.

## Tests

**`src/features/subsidy/api/subsidy-applications.test.ts`:**

- `[SUBS-004]`:
  - a start lands at stage 4 today, wins the lead, stores the calculation, and replays on its key;
  - refusals: not subsidised, a category that doesn't apply, already forwarded, a calculation field under `calculation.`.
- `[SUBS-005]`:
  - the list with its status, search and lead filters;
  - a dealer gets 403.
- `[SUBS-006]`:
  - the stages in order; a Reg. No.; a remark wanted going back; paise checked;
  - closing once every amount has its date, then 409;
  - cancel, refused to a view-only role.

**`src/features/subsidy/components/applications-ui.test.tsx`:**

- a state with no scheme, and a scheme that isn't ready;
- the calculator asking for the lead's scheme;
- no PIMS sheet on another scheme's application;

- the worklist;
- recording a stage: the remark, a paise mistake, then the entry in the history;
- cancel with a reason;
- a view-only Regional Manager;
- a file over 10 MB refused before sending;
- starting from a lead's card;
- why a commercial lead can't.

**By hand, in Chromium on the mock backend, as a field employee:**

1. The worklist.
2. A lead's card, then started from it.
3. A stage refused, then recorded.
4. The stored calculation.
5. The PIMS download.
6. The worklist and an application on a 360 px phone in dark mode.

axe found nothing on any of these. `npm run build` passes, the prerendered calculator included.
