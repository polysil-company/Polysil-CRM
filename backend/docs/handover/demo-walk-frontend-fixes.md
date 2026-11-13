# Demo walk: frontend fixes before the demo

> A walk of staging on 1 Oct, along the demo's path. The backend fixed its side (the customer link and the PDFs). These are the frontend's, most urgent first.

## D-1 · The dashboard fails for every role (blocks the demo)

`GET /api/v1/dashboard/overview` answers 200, and `getDashboardOverview` rejects the body as a contract violation. `dashboard.schemas.ts` still carries `TODO(RPT-001): agree the dashboard contract`. It describes a camelCase shape with numbers. The backend has served its own shape since BE-008, documented in `backend/docs/api/dashboard.md`.

Replace the schema with the backend's shape and map it in the components. Field by field:

| Frontend expects | Backend sends | Note |
|---|---|---|
| `periodLabel` | `period_label` | also `period: {start, end}`, IST dates |
| `kpis.pipelineValue` | `kpis.pipeline_value` | |
| `kpis.newLeads` | `kpis.new_leads` | |
| `kpis.conversionRate` | `kpis.conversion_rate` | a percentage |
| `kpis.overdueFollowUps` | `kpis.overdue_follow_ups` | |
| each KPI `value: number` | `value: string \| null` | a **decimal string**; null only where the role has no such figure |
| each KPI `deltaPercent: number \| null` | `delta_percent: string \| null` | decimal string |
| each KPI `trend: number[]` | `trend: string[]` | decimal strings, oldest first |
| `pipeline[].status` | `pipeline[].stage` | every stage but `merged`, in lifecycle order |
| `pipeline[].value: number` | `pipeline[].value: string` | decimal string |
| `sources[]` `{source, name, count}` | the same | `count` an integer |
| `followUps[]` | `follow_ups[]` | |
| `followUps[].leadId` | `lead_id` | also `task_id` |
| `followUps[].customerName` | `farmer_name` | |
| `followUps[].district: string` | `district: string \| null` | null when the lead has no district above it |
| `followUps[].dueAt` | `due_at` | ISO timestamp |
| `followUps[].ownerName` | `assigned_to.full_name` | `assigned_to` may be null |
| (none) | `follow_ups[].overdue: boolean` | due before today in IST |

Parse money and percentages as strings (`Number()` only for chart drawing). That keeps rule 4: no float for money anywhere it is shown.

## D-2 · The customer's quotation link (fixed on the backend; check only)

The backend now serves the public routes under `/api/v1/public/...` as well, so `GET /api/v1/public/q/<token>` answers. Take the PDF link from the response's `pdf_url`, which is now `/api/v1/public/q/<token>/pdf`. Don't build it. Once backend PR 40 is merged and deployed, nothing else is needed.

## D-4 · The quotation page never shows "Open PDF" without a reload

After sending, the banner says the page checks again by itself. The network tab showed no polling request in 20 seconds. Poll `GET /quotations/{id}` every few seconds while `pdf_state` is `pending`, and stop on `ready` or `failed`. The same applies to an order's `pdf_state` after approval.

## D-6 · Vague lines in the lead history

The events carry what the screen leaves out:
- **`approval.decided`:** `payload.seq`, `payload.role` and `payload.decision`. Show "Asha Patel approved (District Manager step)" or "rejected".
- **`dispatch.recorded`:** `payload.dispatch_no` and `payload.lines`. Show the dispatch number.
- **Order events** sit on the order (`entity_type: sales_order`). The order number is on the order, so link to it.

## D-7 · The duplicate count

The create toast says "Possible duplicate of POL/GJ/2026-27/00076", while the lead page says "3 possible duplicates". Show the count in the toast, or name all of them.

## D-8 · The new-lead form

- It has no crops or land fields, though the lead page shows both. The backend takes them on create (BE-005).
- "Choose the inquiry type" and "Choose the irrigation system" show in red the moment the dropdown opens, over the option list. Validate on blur or on submit.

## D-9 · The first click is sometimes ignored

The approvals inbox's Approve button and the account menu ignored the first click after a page load on two accounts. It may be the test automation clicking before hydration. Worth one check by hand.

## Polish

- **Em dashes in UI copy** (the project's copy rule is no em dashes):
  - "Capture the enquiry now — quotations can be added later."
  - "Say why — the person who asked reads it"
  - "Within the state — CGST and SGST"
  - "Left empty, it's recorded from who you are — Employee for staff."
- **The Accounts remark:** the error for a missing remark on an Accounts *approval* says "Say why — the person who asked reads it". That wording fits a rejection. On the Accounts step, the remark is the payment check.
- **Money formats:**
  - the leads list mixes "₹69,910" and "₹2.41 L" in one column;
  - the quotation card on a lead shows "₹8,763" with no paise.
- **A won lead** still shows the "Warm" tag and "Win probability: Not recorded yet".
- **Toasts:** a toast survives signing out and in as someone else.
