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
| `DOC` | Documents on records — purchase orders, payment slips, invoices, photos |
| `TASK` | Tasks and daily work |
| `CHNL` | Channel partners — distributor, dealer, sub-dealer |
| `TGT` | Sales targets and achievement |
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
| APP-006 | Route guards — a page the user may not open shows access denied, not the page | frontend | in-progress |
| APP-007 | Release menu — a deployment shows and opens only the screens it releases | frontend | in-progress |
| OBS-001 | Logger utility with runtime log level | frontend | in-progress |
| OBS-002 | API client — request IDs, error normalisation, response contract validation | shared | in-progress |
| DS-001 | Design tokens and component library | frontend | in-progress |
| AUTH-001 | Mobile sign-in with a one-time code — channel partners (`POST /auth/otp/request`, `POST /auth/otp/verify`) | shared | mocked |
| AUTH-002 | Current session — user, role, organisation unit, partner and permissions (`GET /auth/me`) | shared | mocked |
| AUTH-003 | Email and password sign-in — Polysil staff (`POST /auth/login`) | shared | mocked |
| AUTH-004 | Keep signed in — rotate the access token with the refresh cookie (`POST /auth/refresh`) | shared | mocked |
| AUTH-005 | Sign out (`POST /auth/logout`) | shared | mocked |
| AUTH-006 | Signed-in routing — sign-in redirects, return path and session end | frontend | in-progress |
| AUTH-007 | Change your own password — forced while a temporary password is in force (`POST /auth/password`) | shared | in-progress |
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
| LEAD-015 | Dealership enquiries — won from qualified, starting a dealer application (`POST /leads/{id}/transition`) | shared | in-progress |
| RPT-001 | Dashboard overview (`GET /dashboard/overview`) | shared | in-progress |
| RPT-002 | Reports — conversion, people, lost leads, follow-ups, dealers, campaigns, areas, complaints (`GET /reports/*`) | shared | in-progress |
| RPT-003 | A lead's 360° view (`GET /leads/{id}/360`) | shared | in-progress |
| TGT-001 | Targets — the month's achievement, yours and your team's (`GET /targets/achievement`) | shared | in-progress |
| TGT-002 | Set a person's monthly targets, with their history (`GET /targets`, `PUT /targets`) | shared | in-progress |
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
| QUOT-014 | A subsidised quotation's subsidy, for one farmer category (`PUT /quotations/{id}/subsidy`, `GET /quotations/{id}/subsidy/calculation`) | shared | in-progress |
| SO-001 | Sales orders list (`GET /orders`) | shared | in-progress |
| SO-002 | A sales order — the document, its approval chain, PDF and history (`GET /orders/{orderId}`, `GET /orders/{orderId}/pdf`, `GET /orders/{orderId}/timeline`) | shared | in-progress |
| SO-003 | New order from accepted quotations, and a draft's header (`POST /orders`, `PATCH /orders/{orderId}`, `DELETE /orders/{orderId}`) | shared | in-progress |
| SO-004 | Submit an order for approval, and cancel it (`POST /orders/{orderId}/submit`, `POST /orders/{orderId}/cancel`) | shared | in-progress |
| SO-005 | A direct order typed in line by line, and a draft's lines (`POST /orders`, `PUT /orders/{orderId}/lines`, `POST /pricing/quote-lines`) | shared | in-progress |
| SO-006 | Export the order list to Excel (`GET /orders/export`) | shared | in-progress |
| SO-007 | Amend an approved order (`POST /orders/{orderId}/amend`) | shared | in-progress |
| SO-008 | A subsidised order: from a subsidised quotation, its subsidy block, and editing it on a draft (`POST /orders`, `PUT /orders/{id}/subsidy`) | shared | in-progress |
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
| CMPL-010 | Reopen a closed or QC-rejected complaint, with a reason (`POST /complaints/{id}/reopen`) | shared | in-progress |
| TASK-001 | My day — one person's tasks due that day and overdue (`GET /planner`) | shared | in-progress |
| TASK-002 | Team day — due, done and overdue per person below a manager (`GET /planner/team`) | shared | in-progress |
| TASK-003 | List tasks — a lead's tasks, and every task with filters (`GET /tasks`, `GET /tasks/{id}`) | shared | in-progress |
| TASK-004 | Create a task — call, visit, meeting, follow-up (`POST /tasks`, `GET /tasks/assignees`, `GET /lookups/meeting-types`) | shared | in-progress |
| TASK-005 | Complete, cancel or reopen a task (`POST /tasks/{id}/complete`, `/cancel`, `/reopen`) | shared | in-progress |
| TASK-006 | Edit or reassign an open task (`PATCH /tasks/{id}`) | shared | in-progress |
| TASK-007 | Meeting minutes with action items (`POST /minutes`, `GET /minutes`, `GET /minutes/{id}`) | shared | in-progress |
| TASK-008 | Export the task list to Excel (`GET /tasks/export`) | shared | in-progress |
| CHNL-001 | Channel partners list and detail, with the Excel export (`GET /partners`, `/partners/{id}`, `/partners/export`) | shared | in-progress |
| CHNL-002 | Add a channel partner — a distributor, or a dealer or sub-dealer under one (`POST /partners`) | shared | in-progress |
| CHNL-003 | Correct a channel partner's details and credit terms (`PATCH /partners/{id}`) | shared | in-progress |
| CHNL-004 | Close or reopen a channel partner (`POST /partners/{id}/close`, `/reopen`) | shared | in-progress |
| CHNL-005 | Import channel partners from Excel (`/imports` with `kind=partners`) | shared | in-progress |
| CHNL-006 | GSTIN details — fill a partner's names from the GST record (`GET /gstin/{gstin}`) | shared | in-progress |
| CHNL-007 | Dealer applications — start one, fill it for the applicant, and decide (`/dealer-applications`, `…/submit`, `…/withdraw`, `…/link`, `…/decision`) | shared | in-progress |
| CHNL-008 | The dealer applicant's own page — verify the mobile, fill in, upload, submit (`/public/dealer-apply/{token}`, `…/verify`, `…/documents`, `…/submit`) | shared | in-progress |
| MKT-001 | Marketing offers — set by Admin, visible to channel partners only | shared | planned |
| SCHM-001 | Schemes — the list and a scheme (`GET /schemes`, `GET /schemes/{id}`) | shared | in-progress |
| SCHM-002 | Create and change a scheme (`POST /schemes`, `PATCH /schemes/{id}`) | shared | in-progress |
| SCHM-003 | A period scheme's standing (`GET /schemes/{id}/standing`) | shared | in-progress |
| SCHM-004 | Scheme credits (`GET /scheme-entitlements`) | shared | in-progress |
| SCHM-005 | Scheme benefits on an order: the preview on a draft, the benefits and To pay after submit (`GET /orders/{id}/schemes`, `benefits` and `payable` on `GET /orders/{id}`) | shared | in-progress |
| MSTR-001 | Masters — the Admin → Masters area: lists, lead scoring and offices (`/masters`) | shared | in-progress |
| MSTR-002 | Lead lookups — sources, irrigation systems, lost reasons and the territory picker (`GET /lookups/*`) | shared | in-progress |
| MSTR-003 | Product picker — search the catalogue (`GET /products`) | shared | in-progress |
| MSTR-004 | Product catalogue — browse, add and correct products (`GET`/`POST /products`, `GET`/`PATCH /products/{id}`) | shared | in-progress |
| MSTR-005 | Tax classification — a product's HSN code and each code's GST slab, from a date (`/products/{id}/hsn`, `/tax-rates`) | shared | in-progress |
| MSTR-006 | Price lists — draft, fill the rate sheet, publish, close (`/price-lists*`) | shared | in-progress |
| MSTR-007 | Excel import with column matching — price list rates, partners, order and quotation lines (`/imports*`) | shared | in-progress |
| MSTR-008 | Price lists by sale type — commercial, industrial or subsidised (`sales_type` on `/price-lists`, `/pricing/quote-lines`) | shared | in-progress |
| MSTR-009 | Masters lists — add a row, switch it on or off (`POST /lookups/{list}`, `PATCH /lookups/{list}/{id}`) | shared | in-progress |
| MSTR-010 | Lead scoring — the weights, caps and thresholds behind a lead's score (`GET`/`PATCH /lookups/scoring`) | shared | in-progress |
| MSTR-011 | Offices — the office tree: add, rename, move, close and reopen (`/org-units*`) | shared | in-progress |
| MSTR-012 | Territories — the state, district, taluka and village tree: add, rename, set codes (`GET /territories`, `POST /territories`, `PATCH /territories/{id}`) | shared | in-progress |
| MSTR-013 | Import polish — the blank template, upload errors on their fields, and a price list started from Excel (`GET /imports/template`, `POST /imports`, `POST /price-lists`) | frontend | in-progress |
| DOC-001 | Documents on a lead, quotation, order or dispatch — the list, the types and opening one (`GET /documents`, `/leads/{id}/documents`, `/documents/types`, `/documents/{id}/link`) | shared | in-progress |
| DOC-002 | Attach a document to a record (`POST /documents`) | shared | in-progress |
| DOC-003 | Remove a document (`DELETE /documents/{id}`) | shared | in-progress |
| SUBS-001 | Subsidy forms and case status | shared | planned |
| SUBS-002 | Subsidy calculator — the scheme's cost blocks and every farmer category's share (`POST /subsidy/calculate`) | shared | in-progress |
| SUBS-003 | Subsidy scheme lookups — what each system accepts, the crops and the categories (`GET /subsidy/config`, `GET /subsidy/crops`, `GET /subsidy/categories`) | shared | in-progress |
| SUBS-004 | Start a subsidy application from a lead — the calculation and the farmer's category (`POST /subsidy-applications`, `GET /subsidy-schemes/for-lead/{leadId}`) | shared | in-progress |
| SUBS-005 | Subsidy applications worklist, with its Excel export (`GET /subsidy-applications`, `GET /subsidy-applications/export`) | shared | in-progress |
| SUBS-006 | A subsidy application — its figures, stored calculation, stages and cancel (`GET /subsidy-applications/{id}`, `GET /subsidy-applications/{id}/calculation`, `GET /subsidy-applications/{id}/stages`, `POST /subsidy-applications/{id}/stages`, `POST /subsidy-applications/{id}/cancel`, `GET /subsidy-stages`) | shared | in-progress |
| SUBS-007 | A subsidy application's document checklist and uploads (`GET /subsidy-applications/{id}/documents`, `POST /subsidy-applications/{id}/documents`, `GET /subsidy-applications/{id}/documents/{docId}`, `GET /subsidy-document-types`) | shared | in-progress |
| SUBS-008 | Download a subsidy application's PIMS sheet (`GET /subsidy-applications/{id}/pims.xlsx`) | shared | in-progress |
| SUBS-009 | Subsidy ageing — the client's six ageing figures per application, with its export (`GET /subsidy-reports/ageing`, `GET /subsidy-reports/ageing/export`) | shared | in-progress |
| SUBS-010 | Subsidy stage report — applications and money in each stage, with its export (`GET /subsidy-reports/stages`, `GET /subsidy-reports/stages/export`) | shared | in-progress |
| SUBS-011 | Subsidy supply report — supplied and not supplied by district, with its export (`GET /subsidy-reports/supply`, `GET /subsidy-reports/supply/export`) | shared | in-progress |
| SUBS-012 | Subsidy masters — categories, parameters, component rates and crop spacings, revised from a date (`GET /subsidy-masters/{kind}`, `POST /subsidy-masters/{kind}/revisions`) | shared | in-progress |
| SUBS-013 | Subsidy matrices — the unit-cost and quantity matrices in force, and a new one from a date (`GET /subsidy-masters/{kind}/matrices`, `POST /subsidy-masters/{kind}/matrices`) | shared | in-progress |
| SUBS-014 | Subsidy schemes — a state's scheme set up, its readiness, stage names and switching off (`GET /subsidy-schemes`, `POST /subsidy-schemes`, `GET /subsidy-schemes/{code}`, `PATCH /subsidy-schemes/{code}`, `PATCH /subsidy-schemes/{code}/stages/{stageCode}`) | shared | in-progress |
| ACCT-001 | Accounts work queue (`GET /orders?waiting_on=account_manager`, `GET /orders/stats`, `GET /orders/export`) | shared | in-progress |
| ACCT-002 | Record a payment, spread over a dealer's orders (`POST /payments`) | shared | in-progress |
| ACCT-003 | Receipts for Accounts: allocate the rest, void (`GET /payments`, `/payments/{id}/allocations`, `/void`) | shared | in-progress |
| ACCT-004 | An order's payments and instalments (`payments` on `GET /orders/{id}`, `PUT /orders/{id}/payment-schedule`) | shared | in-progress |
| ACCT-005 | A dealer's ledger and credit (`GET /partners/{id}/ledger`, `/credit`) | shared | in-progress |
| SUBS-015 | Reopen a closed subsidy application, with a reason (`POST /subsidy-applications/{id}/reopen`) | shared | in-progress |
| SUBS-016 | Dealer commission and TOD on an application, stage 18 (`GET`/`POST /subsidy-applications/{id}/commission`, `/commission/preview`) | shared | in-progress |
| SUBS-017 | Dealer commissions for Accounts: approve, return, cancel, pay, Excel (`/dealer-commissions*`) | shared | in-progress |
| SUBS-018 | Commission rates by scheme, from a date (`GET`/`POST /commission-rates`) | shared | in-progress |
| DISP-001 | Dispatch work queue — orders to ship, and the dispatch log (`GET /orders?status=approved,partially_dispatched`, `GET /dispatches`) | shared | in-progress |
| DISP-002 | Record a dispatch on an order, void it, close the rest short (`POST /orders/{orderId}/dispatches`, `POST /dispatches/{dispatchId}/void`, `POST /orders/{orderId}/close-short`) | shared | in-progress |
| ADMN-001 | People — the list of staff and partner users, with filters and an Excel export (`GET /users`, `GET /users/export`) | shared | in-progress |
| ADMN-002 | A person — identity, role, office or partner, territories, sign-in state (`GET /users/{id}`) | shared | in-progress |
| ADMN-003 | Add a person — a staff member with a temporary password, or a partner user (`POST /users`, `GET /lookups/roles`, `GET /org-units`) | shared | in-progress |
| ADMN-004 | Correct a person — details, role, office, territories; deactivate or reactivate (`PATCH /users/{id}`) | shared | in-progress |
| ADMN-005 | Account actions — a new temporary password, sign out everywhere, unlock (`POST /users/{id}/password`, `/sessions/revoke`, `/unlock`) | shared | in-progress |
| ADMN-006 | A leaver — hand over their open leads and tasks, then deactivate or delete (`POST /users/{id}/handover`, `DELETE /users/{id}`) | shared | in-progress |
| ADMN-007 | Company settings — how amended orders are re-approved, and complaint reopening (`GET /settings`, `PATCH /settings`) | shared | in-progress |
| SITE-001 | Public website — information, Product Master, phone-number entry | shared | planned |
| NOTIF-001 | In-app notifications — bell, latest notifications and unread count | shared | in-progress |
| NOTIF-002 | Mark notifications as read — one or all | shared | in-progress |
| MSG-001 | Conversation list with unread counts | shared | in-progress |
| MSG-002 | Messages in a conversation | shared | in-progress |
| MSG-003 | Send a message, optionally linking a CRM record | shared | in-progress |
| MSG-004 | Start or read one conversation — staff directory search | shared | in-progress |
| MSG-005 | Mark a conversation as read | shared | in-progress |
| MSG-006 | Group chats — start a group, rename it, add, remove and leave (`POST /conversations/groups`, `PATCH /conversations/{id}`, `/conversations/{id}/members`) | shared | in-progress |
| REPO-001 | Changelog system — one entry per change, generated CHANGELOG.md | frontend | in-progress |
| REPO-002 | Quality gates — lint rules, git hooks, CI pipeline | frontend | in-progress |
