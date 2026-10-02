---
date: 2026-10-02
type: fix
title: "Demo walk fixes: the dashboard on the backend's contract, the customer's PDF
  link, crops and land, clearer lead history"
dataIds:
  - RPT-001
  - QUOT-012
  - LEAD-002
  - LEAD-003
  - LEAD-005
  - APPR-001
  - AUTH-005
author: Nakul Srivastava
breaking: false
---

## Before

The backend's walk of staging on 1 October, along the demo's path, found these (most urgent first):

- **The dashboard failed for every role (D-1).** Its contract was a guess from before the backend had a dashboard: camelCase, numbers. The backend sends snake_case with decimal strings (BE-008), so every answer was rejected as a contract violation.
- **The customer's PDF link would break (D-2).** The backend now sends `pdf_url` as `/api/v1/public/q/…/pdf`. The page put the API base in front again, giving `/api/v1/api/v1/…`.
- **Vague lead history (D-6).** It said "Approval decided" or "Sales order submitted", without the step, the decision, the quotation's number or the dispatch number.
- **The duplicate count (D-7).** The create toast named one possible duplicate while the lead page said "3 possible duplicates".
- **The new-lead form (D-8):**
  - it had no crops or land, though the backend takes both (BE-003);
  - "Choose the inquiry type" and "Choose the irrigation system" showed in red the moment a dropdown opened.
- **Polish:**
  - em dashes in UI copy;
  - the Accounts remark error read like a rejection;
  - the leads list mixed "₹69,910" and "₹2.41 L";
  - a lead's quotation card showed no paise;
  - a won lead still showed "Warm" and an empty "Win probability" card;
  - a toast survived signing out and in as someone else.

## Now

**Dashboard (RPT-001).** It reads the backend's own shape from `backend/docs/api/dashboard.md`:

- **Money stays a decimal string** until it is printed. Counts and percentages become numbers only for display and the sparklines.
- **Snapshot figures** (open pipeline, overdue follow-ups) show no change or trend, because the backend sends none.
- **Follow-ups** are the backend's tasks, with district, assignee (or "Unassigned") and an "Overdue" mark.
- **The mock answers in the same shape.** In partial mode the dashboard goes to the real backend.

**The customer's PDF link (QUOT-012).** A path from an answer is used as given. `asApiPath` strips the backend's own `/api/v1` prefix, so the base is never added twice. Older answers without the prefix keep working.

**Lead history (LEAD-005):**

- **Approvals:** "Ravi Joshi approved the District Manager step" (or "returned it at …"), with Accounts and Dispatch named by their desks.
- **Quotation events:** the number and version as a link ("QT/GJ/2026-27/00009 · v2"), from the fields the backend added in BE-017.
- **Dispatch events:** the dispatch number.
- **Order events:** they link to the order once the backend names it (BE-020, asked here). Until then they say what happened.

**Duplicates (LEAD-002).** The toast names every pending duplicate: "3 possible duplicates (A, B and C), flagged for review".

**New lead form (LEAD-002):**

- **Crops:** up to 10 from the admin-edited list (`GET /lookups/crops`), shown as "Cotton, Groundnut and 1 more".
- **Land:** in acres, e.g. 4.5.
- **Dropdowns** are checked on submit, then as they change, never just for being opened.

**Lead page and list (LEAD-003):**

- **Crops** show as tags (a switched-off crop greyed) beside the land in acres.
- **Win probability and engagement** (the cards and the list's two columns) are gone, as the backend decided (BE-004).
- **Hot, warm or cold** shows only while a lead is open.
- **The list** shows its crops and every value in whole rupees.

**Copy and polish:**

- **Em dashes:** no em dash remains in UI copy.
- **Accounts remark (APPR-001):** an Accounts approval asks for its **payment check** ("Note the payment check: what was received or agreed"); a return still asks why.
- **Money:** the lead's quotation card shows paise.
- **Toasts (AUTH-005):** they clear on sign-out and on sign-in.

## Discussion

- **D-4** (no polling for "Open PDF") **and D-9** (first click ignored) need no code. The quotation and order pages already poll every 3 seconds while a PDF renders (`quotations.queries.ts`, `orders.queries.ts`); the walk likely ran an older build, or a PDF that never left `pending`. D-9 looks like the test robot clicking before the page hydrated. Both are to be checked by hand.
- **Order links in the lead's history** need the backend: its order events carry `{}` or no order id. Asked as **BE-020**; the frontend reads `order_id` and `order_no` as soon as they arrive.
- **Notifications and messages** are still mocked (BE-009, BE-010 are served). They connect in the next pull request, with sorting (BE-001), territory levels (BE-005) and assignment names (BE-006).
- **Mock leads** take their crops and land from their position, not the random seed, so no other seeded figure moved.

## Files changed

- `src/features/dashboard/api/dashboard.schemas.ts` — the backend's shape, `figure`, `trendPoints`; `components/dashboard-overview.tsx` — reads it; `src/mocks/handlers/dashboard.ts` — answers in it; `handlers/index.ts` — the dashboard leaves `unbuiltHandlers`
- `src/lib/api/url.ts` — `asApiPath` takes the backend's `/api/v1` prefix; `src/mocks/handlers/quotations.ts` — `pdf_url` as the backend sends it
- `src/features/leads/lib/timeline-entries.ts`, `components/lead-timeline.tsx` — approval, quotation, order and dispatch lines
- `src/features/leads/lib/lead-labels.ts` — `describeCreatedLead` (every duplicate), `formatAcres`; `components/new-lead-dialog.tsx` — crops, land, dropdowns validated on submit
- `src/features/lookups/components/crop-picker.tsx` — new; `api/lookups.schemas.ts` — `crops` list
- `src/features/leads/api/leads.schemas.ts` — `crops`, `land_acres` on the lead and the create request; `lib/create-lead-errors.ts`
- `src/features/leads/components/lead-detail.tsx`, `leads-columns.tsx`, `lib/lead-table-layout.ts` — crops and land; win probability and engagement removed; priority only on open leads; whole rupees
- `src/features/approvals/` — `missingRemarkMessage`, the payment check on an Accounts approval
- `src/features/auth/components/auth-gate.tsx`, `sign-in-screen.tsx` — toasts cleared
- UI copy across `quotations`, `orders`, `leads`, `lookups`, `messages`, `layout` and `app` — no em dashes; `lead-quotations.tsx` — paise
- `src/mocks/data/leads.ts`, `data/lookups.ts`, `handlers/leads.ts` — crops and land
- `src/lib/data-ids/registry.ts`, `Docs/Data-IDs.md` — RPT-001 in progress
- `Docs/Plan.md` §9, `Docs/Tested-Features.md`, `../docs/Backend-Tasks.md` (BE-020), `Docs/screenshots/demo-fixes/`

## Tests

- `src/features/dashboard/api/dashboard.test.ts` — `[RPT-001]` the backend's shape read with money as strings; the old shape refused as a contract violation; the mock answers the same way; figures and trends
- `src/lib/api/url-and-errors.test.ts` — `[QUOT-012]` `asApiPath` with and without the backend's prefix, never a double base, other hosts refused
- `src/features/leads/lib/timeline-entries.test.ts`, `components/lead-activity.test.tsx` — `[LEAD-005]` approval steps, quotation links, dispatch numbers; `[LEAD-003]` crops and land, no win probability, no priority on a won lead
- `src/features/leads/lib/lead-labels.test.ts` — `[LEAD-002]` one or several duplicates
- `src/features/leads/components/leads-ui.test.tsx` — `[LEAD-002]` a dropdown opened is not marked wrong (fails with the old `onBlur`); crops and land sent with the lead
- `src/features/leads/api/leads.test.ts` — crops and land in the request; their field errors
- `src/features/approvals/lib/approval-labels.test.ts` — `[APPR-001]` the reason to return and the Accounts payment check
- `src/features/auth/components/auth-gate.test.tsx` — `[AUTH-006]` no toast survives a sign-out (fails without the fix)
- `src/mocks/handlers/index.test.ts` — the dashboard goes to the real API in partial mode
- `e2e/smoke.spec.ts` — the whole suite, desktop and phone, with axe: 35 passed
- By hand (`npm run dev`): the dashboard on a desktop and a phone in dark mode; a new lead with three crops and 4.5 acres, a dropdown opened and closed without an error; a won lead with its crops and land and no "Warm". axe found nothing.
