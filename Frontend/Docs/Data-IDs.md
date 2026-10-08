# Data IDs

**Source of truth:** [`src/lib/data-ids/registry.ts`](../src/lib/data-ids/registry.ts)

A **Data ID** names one functionality — an API operation, a screen action, or a cross-cutting
capability — with the same identifier on the frontend and the backend. When something breaks, the
ID tells you *which functionality*, and the request ID tells you *which request*, on both sides.

---

## Format

`DOMAIN-NNN` — for example `LEAD-002`.

| Domain | Covers |
|---|---|
| `APP` | Application shell, navigation, theming, route transitions |
| `OBS` | Observability — logging, API tracing, error reporting |
| `DS` | Design system — tokens and component library |
| `AUTH` | Authentication, session and permissions |
| `LEAD` | Lead generation and management |
| `QUOT` | Quotations |
| `SO` | Sales orders |
| `APPR` | Approvals — amount-based escalation |
| `CMPL` | Complaints and QA review |
| `TASK` | Tasks and daily work |
| `CHNL` | Channel partners — distributor, dealer, sub-dealer |
| `MKT` | Marketing and promotional offers |
| `SCHM` | Schemes |
| `MSTR` | Masters — products, stock, price lists, territories |
| `RPT` | Reports and dashboards |
| `SUBS` | Subsidy forms and case status |
| `ACCT` | Accounts — payments, ledgers, financial approval queue |
| `DISP` | Dispatch — stock, dispatch and delivery queue |
| `ADMN` | Administration — users, roles, thresholds, handover |
| `NOTIF` | Notifications — in-app bell, WhatsApp and email |
| `MSG` | Messages — direct conversations between staff |
| `BOT` | AI assistant |
| `SITE` | Public website |
| `REPO` | Repository tooling — changelog, lint rules, git hooks, CI |

Each entry records a title, an owner (`frontend`, `backend` or `shared`), a status and, for API
work, its endpoints.

| Status | Meaning |
|---|---|
| `planned` | Registered, not started |
| `in-progress` | Being built |
| `mocked` | Frontend complete against MSW mocks; waiting for the real endpoint |
| `integrated` | Running against the real backend in staging |
| `deprecated` | Retired — the ID is never reused |

---

## Rules

1. **Register the ID before you write the code.** Add it to `registry.ts` in the same PR.
2. **Agree it with the backend developer** for anything with an endpoint: the backend uses the
   identical ID for that endpoint.
3. **Never reuse or renumber.** Retired IDs stay in the registry as `deprecated`.
4. **One functionality, one ID.** List, create and detail are separate IDs (`LEAD-001`, `LEAD-002`,
   `LEAD-003`) because they fail independently.
5. **Update the status** as work moves from `planned` to `integrated`.

---

## Where a Data ID appears

| Place | Example | Enforced by |
|---|---|---|
| API request header | `x-data-id: LEAD-001` | `apiRequest()` requires `dataId` (type error without it) |
| Request correlation | `x-request-id: 3f2a9c1e-…` | Generated per call by `apiRequest()` |
| Every log line | `[LEAD-001] features/leads/api/leads.api.ts → listLeads → ← GET /leads 200 · 132ms` | `createLogger({ file, dataId })` |
| TanStack Query metadata | `meta: { dataId: "LEAD-001" }` | Typed `Register` in `lib/query/query-client.ts` |
| Error reference shown to users | `LEAD-001 · 3f2a9c1e-…` (copy button) | `<ErrorState>` |
| Test names | `describe("[LEAD-001] leads list", …)` | Lint rule `local/test-describe-data-id` |
| Changelog entries | `dataIds: [LEAD-001]` | `npm run changelog:check` (IDs must exist) |
| Commits | `feat(LEAD-001): add status filter` | commitlint `scope-data-id` |
| Branches | `feature/LEAD-001-status-filter` | Convention |

---

## Tracing a problem in five minutes

1. **Get the reference.** The user copies it from the error screen: `LEAD-001 · 3f2a9c1e-…`.
2. **Frontend logs.** Search for the request ID. The log shows the file, function, request (query,
   redacted body), response status and duration — or the error kind:
   - `network` / `timeout` → connectivity or the backend is down
   - `http` 5xx → backend
   - `http` 4xx → the request was rejected — usually frontend input, state or permissions
   - `contract` (`CONTRACT_VIOLATION`) → the backend answered 2xx with a body that breaks the agreed
     schema. The log lists which fields failed (never the values).
3. **Backend logs.** Search the same request ID. The backend logs `x-request-id` and `x-data-id`.
4. **Code.** Search the Data ID across the repo: it leads to the API function, query options, mock
   handler, components, tests and the changelog entries that touched it.

---

## Backend agreement checklist

Ask the backend to:

- Accept and log `x-request-id` and `x-data-id` on every request, and return `x-request-id` in the
  response (CORS: allow those request headers and expose `x-request-id`).
- Use the same Data ID for the matching endpoint in their route definitions and logs.
- Return errors in RFC 9457 problem-details format (`{ type, title, status, detail, code, errors }`),
  with field errors under `errors` for 422 responses.

TODO(OBS-002): when an OpenAPI specification exists, record Data IDs as an `x-data-id` extension on
each operation and generate this registry from it.

---

## Current registry (snapshot)

The registry file is the source of truth; this snapshot helps reading.

| ID | Title | Owner | Status |
|---|---|---|---|
| APP-001 | App shell — sidebar, header, role-filtered navigation, command menu | frontend | in-progress |
| APP-002 | Theme — light, dark and system preference | frontend | in-progress |
| APP-003 | Route transitions, page skeletons and route-level error boundaries | frontend | in-progress |
| APP-004 | Mock scenarios for previewing loading, empty, error and contract states | frontend | in-progress |
| APP-005 | Collapsible desktop sidebar and page titles in the top bar | frontend | in-progress |
| OBS-001 | Logger utility with runtime log level | frontend | in-progress |
| OBS-002 | API client — request IDs, error normalisation, response contract validation | shared | in-progress |
| DS-001 | Design tokens and component library | frontend | in-progress |
| AUTH-001 | Mobile sign-in with a one-time code — channel partners (`POST /auth/otp/request`, `POST /auth/otp/verify`) | shared | mocked |
| AUTH-002 | Current session — user, role, organisation unit, partner and permissions (`GET /auth/me`) | shared | mocked |
| AUTH-003 | Email and password sign-in — Polysil staff (`POST /auth/login`) | shared | mocked |
| AUTH-004 | Keep signed in — rotate the access token with the refresh cookie (`POST /auth/refresh`) | shared | mocked |
| AUTH-005 | Sign out (`POST /auth/logout`) | shared | mocked |
| AUTH-006 | Signed-in routing — sign-in redirects, return path and session end | frontend | in-progress |
| LEAD-001 | List leads with filters, sorting and pagination (`GET /leads`, `GET /leads/areas`) | shared | in-progress |
| LEAD-002 | Create lead (`POST /leads`) | shared | in-progress |
| LEAD-003 | Lead detail (`GET /leads/{leadId}`) | shared | in-progress |
| LEAD-004 | Lead stats — navigation badge and sales tab (`GET /leads/stats`) | shared | in-progress |
| LEAD-005 | Lead timeline — the lead's history, newest first (`GET /leads/{leadId}/timeline`) | shared | in-progress |
| LEAD-006 | Add a note to a lead (`POST /leads/{leadId}/notes`) | shared | in-progress |
| LEAD-007 | Move a lead's stage — contact, qualify, mark lost, reopen (`POST /leads/{leadId}/transition`, `POST /leads/{leadId}/reopen`) | shared | in-progress |
| LEAD-008 | Assign a lead — owner and channel partner (`POST /leads/{leadId}/assign`, `GET /leads/assignees`, `GET /lookups/partners`) | shared | in-progress |
| LEAD-009 | Export the lead list to Excel (`GET /leads/export`) | shared | in-progress |
| LEAD-010 | Edit a lead's own fields (`PATCH /leads/{leadId}`) | shared | in-progress |
| LEAD-011 | Delete a lead (`DELETE /leads/{leadId}`) | shared | in-progress |
| LEAD-012 | Duplicate review — dismiss a pair, or merge one lead into the other (`GET /leads/duplicates`, `POST /leads/duplicates/{linkId}/dismiss`, `POST /leads/{leadId}/merge`) | shared | in-progress |
| LEAD-013 | Lead QR codes — make, print, rename or switch off (`GET /lead-qr-codes`, `POST /lead-qr-codes`, `PATCH /lead-qr-codes/{qrId}`) | shared | in-progress |
| LEAD-014 | The public enquiry page — /enquiry, with or without a QR code (`GET /public/lead-form`, `GET /public/territories`, `POST /public/leads/verify`, `POST /public/leads`) | shared | in-progress |
| RPT-001 | Dashboard overview (`GET /dashboard/overview`) | shared | in-progress |
| RPT-002 | Reports | shared | planned |
| QUOT-001 | Quotations list — the Quotations page and a lead's quotations (`GET /quotations`) | shared | in-progress |
| QUOT-002 | Quotation detail — the document as the backend prints it (`GET /quotations/{quotationId}`) | shared | in-progress |
| QUOT-003 | Open a quotation's PDF (`GET /quotations/{quotationId}/pdf`) | shared | in-progress |
| QUOT-004 | Quotation builder — create and edit a draft (`POST /quotations`, `PATCH /quotations/{quotationId}`, `PUT /quotations/{quotationId}/lines`) | shared | in-progress |
| QUOT-005 | Live pricing — the quotation preview (`POST /pricing/quote-lines`) | shared | planned |
| QUOT-006 | Send a quotation — number it, share the link, render the PDF (`POST /quotations/{quotationId}/send`) | shared | in-progress |
| QUOT-007 | Ask a manager to approve a quotation's discount (`POST /quotations/{quotationId}/request-approval`) | shared | in-progress |
| QUOT-008 | Record the customer's answer — accepted, rejected or negotiation (`POST /quotations/{quotationId}/transition`) | shared | in-progress |
| QUOT-009 | Revise a quotation, and its versions (`POST /quotations/{quotationId}/revise`, `GET /quotations/{quotationId}/versions`) | shared | in-progress |
| QUOT-010 | A quotation's history (`GET /quotations/{quotationId}/timeline`) | shared | in-progress |
| QUOT-011 | Delete a draft quotation (`DELETE /quotations/{quotationId}`) | shared | in-progress |
| QUOT-012 | The customer's quotation page — /q/{token} (`GET /public/q/{token}`, `GET /public/q/{token}/pdf`) | shared | in-progress |
| QUOT-013 | Export the quotation list to Excel (`GET /quotations/export`) | shared | in-progress |
| SO-001 | Sales orders list (`GET /orders`) | shared | in-progress |
| SO-002 | A sales order — the document, its approval chain, PDF and history (`GET /orders/{orderId}`, `GET /orders/{orderId}/pdf`, `GET /orders/{orderId}/timeline`) | shared | in-progress |
| SO-003 | New order from accepted quotations, and a draft's header (`POST /orders`, `PATCH /orders/{orderId}`, `DELETE /orders/{orderId}`) | shared | in-progress |
| SO-004 | Submit an order for approval, and cancel it (`POST /orders/{orderId}/submit`, `POST /orders/{orderId}/cancel`) | shared | in-progress |
| SO-005 | A direct order typed in line by line, and a draft's lines (`POST /orders`, `PUT /orders/{orderId}/lines`, `POST /pricing/quote-lines`) | shared | in-progress |
| SO-006 | Export the order list to Excel (`GET /orders/export`) | shared | in-progress |
| APPR-001 | Approval inbox — amount-based escalation (`GET /approvals/pending`, `POST /approvals/steps/{stepId}/decision`) | shared | in-progress |
| APPR-002 | Approval limits — order value and discount per role (`GET /approvals/thresholds`, `PUT /approvals/thresholds`) | shared | in-progress |
| CMPL-001 | Complaints list — filters, waiting on me, counts (`GET /complaints`, `GET /complaints/stats`) | shared | in-progress |
| CMPL-002 | Complaint detail and history (`GET /complaints/{id}`, `GET /complaints/{id}/timeline`) | shared | in-progress |
| CMPL-003 | Raise a complaint — draft, edit, products, submit, cancel, delete (`POST /complaints`, `PATCH /complaints/{id}`, `PUT /complaints/{id}/lines`, `POST /complaints/{id}/submit`, `POST /complaints/{id}/cancel`, `DELETE /complaints/{id}`) | shared | in-progress |
| CMPL-004 | Manager's check — approve or return, severity and owner (`POST /complaints/{id}/check`, `GET /complaints/{id}/assignees`) | shared | in-progress |
| CMPL-005 | QC verdict (`POST /complaints/{id}/qc`) | shared | in-progress |
| CMPL-006 | Complaint attachments — photos and documents (`POST /complaints/{id}/attachments`, `GET /complaints/{id}/attachments/{attachmentId}`, `DELETE /complaints/{id}/attachments/{attachmentId}`) | shared | in-progress |
| CMPL-007 | Complaint remedy — refund, replacement or none; withdraw (`POST /complaints/{id}/remedy`, `POST /complaints/{id}/remedy/withdraw`) | shared | in-progress |
| CMPL-008 | Complaint targets (SLA policies) and complaint types (`GET /complaint-sla-policies`, `POST /complaint-sla-policies`, `GET /lookups/complaint-types`, `POST /lookups/complaint-types`) | shared | in-progress |
| CMPL-009 | Export complaints to Excel (`GET /complaints/export`) | shared | in-progress |
| TASK-001 | My day — one person's tasks due that day and overdue (`GET /planner`) | shared | in-progress |
| TASK-002 | Team day — due, done and overdue per person below a manager (`GET /planner/team`) | shared | in-progress |
| TASK-003 | List tasks — a lead's tasks, and every task with filters (`GET /tasks`, `GET /tasks/{id}`) | shared | in-progress |
| TASK-004 | Create a task — call, visit, meeting, follow-up (`POST /tasks`, `GET /tasks/assignees`, `GET /lookups/meeting-types`) | shared | in-progress |
| TASK-005 | Complete, cancel or reopen a task (`POST /tasks/{id}/complete`, `/cancel`, `/reopen`) | shared | in-progress |
| TASK-006 | Edit or reassign an open task (`PATCH /tasks/{id}`) | shared | in-progress |
| TASK-007 | Meeting minutes with action items (`POST /minutes`, `GET /minutes`, `GET /minutes/{id}`) | shared | in-progress |
| TASK-008 | Export the task list to Excel (`GET /tasks/export`) | shared | in-progress |
| CHNL-001 | Channel partners list and detail | shared | planned |
| MKT-001 | Marketing offers — set by Admin, visible to channel partners only | shared | planned |
| SCHM-001 | Schemes — set by Admin, visible to everyone | shared | planned |
| MSTR-001 | Masters — products, stock, price lists, territories | shared | planned |
| MSTR-002 | Lead lookups — sources, irrigation systems, lost reasons and the territory picker (`GET /lookups/*`) | shared | in-progress |
| MSTR-003 | Product picker — search the catalogue (`GET /products`) | shared | in-progress |
| SUBS-001 | Subsidy forms and case status | shared | planned |
| SUBS-002 | Subsidy calculator — the scheme's cost blocks and every farmer category's share (`POST /subsidy/calculate`) | shared | in-progress |
| SUBS-003 | Subsidy scheme lookups — what each system accepts, the crops and the categories (`GET /subsidy/config`, `GET /subsidy/crops`, `GET /subsidy/categories`) | shared | in-progress |
| SUBS-004 | Start a subsidy application from a lead — the calculation and the farmer's category (`POST /subsidy-applications`) | shared | in-progress |
| SUBS-005 | Subsidy applications worklist, with its Excel export (`GET /subsidy-applications`, `GET /subsidy-applications/export`) | shared | in-progress |
| SUBS-006 | A subsidy application — its figures, stored calculation, stages and cancel (`GET /subsidy-applications/{id}`, `GET /subsidy-applications/{id}/calculation`, `GET /subsidy-applications/{id}/stages`, `POST /subsidy-applications/{id}/stages`, `POST /subsidy-applications/{id}/cancel`, `GET /subsidy-stages`) | shared | in-progress |
| SUBS-007 | A subsidy application's document checklist and uploads (`GET /subsidy-applications/{id}/documents`, `POST /subsidy-applications/{id}/documents`, `GET /subsidy-applications/{id}/documents/{docId}`) | shared | in-progress |
| SUBS-008 | Download a subsidy application's PIMS sheet (`GET /subsidy-applications/{id}/pims.xlsx`) | shared | in-progress |
| SUBS-009 | Subsidy ageing — the client's six ageing figures per application, with its export (`GET /subsidy-reports/ageing`, `GET /subsidy-reports/ageing/export`) | shared | in-progress |
| SUBS-010 | Subsidy stage report — applications and money in each stage, with its export (`GET /subsidy-reports/stages`, `GET /subsidy-reports/stages/export`) | shared | in-progress |
| SUBS-011 | Subsidy supply report — supplied and not supplied by district, with its export (`GET /subsidy-reports/supply`, `GET /subsidy-reports/supply/export`) | shared | in-progress |
| ACCT-001 | Accounts work queue | shared | planned |
| DISP-001 | Dispatch work queue — orders to ship, and the dispatch log (`GET /orders?status=approved,partially_dispatched`, `GET /dispatches`) | shared | in-progress |
| DISP-002 | Record a dispatch on an order, void it, close the rest short (`POST /orders/{orderId}/dispatches`, `POST /dispatches/{dispatchId}/void`, `POST /orders/{orderId}/close-short`) | shared | in-progress |
| ADMN-001 | Users, roles and approval thresholds | shared | planned |
| SITE-001 | Public website — information, Product Master, phone-number entry | shared | planned |
| NOTIF-001 | In-app notifications — bell, latest notifications and unread count | shared | in-progress |
| NOTIF-002 | Mark notifications as read — one or all | shared | in-progress |
| MSG-001 | Conversation list with unread counts | shared | in-progress |
| MSG-002 | Messages in a conversation | shared | in-progress |
| MSG-003 | Send a message, optionally linking a CRM record | shared | in-progress |
| MSG-004 | Start a conversation — staff directory search | shared | in-progress |
| MSG-005 | Mark a conversation as read | shared | in-progress |
| REPO-001 | Changelog system — one entry per change, generated CHANGELOG.md | frontend | in-progress |
| REPO-002 | Quality gates — lint rules, git hooks, CI pipeline | frontend | in-progress |
