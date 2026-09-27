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
| LEAD-001 | List leads with filters, sorting and pagination (`GET /leads`) | shared | in-progress |
| LEAD-002 | Create lead (`POST /leads`) | shared | in-progress |
| LEAD-003 | Lead detail (`GET /leads/{leadId}`) | shared | in-progress |
| LEAD-004 | Lead stats — navigation badge and sales tab (`GET /leads/stats`) | shared | in-progress |
| LEAD-005 | Lead timeline — the lead's history, newest first (`GET /leads/{leadId}/timeline`) | shared | in-progress |
| LEAD-006 | Add a note to a lead (`POST /leads/{leadId}/notes`) | shared | in-progress |
| LEAD-007 | Move a lead's stage — contact, qualify, mark lost, reopen (`POST /leads/{leadId}/transition`, `POST /leads/{leadId}/reopen`) | shared | in-progress |
| LEAD-008 | Assign a lead — owner and channel partner (`POST /leads/{leadId}/assign`, `GET /leads/assignees`, `GET /lookups/partners`) | shared | in-progress |
| RPT-001 | Dashboard overview (`GET /dashboard/overview`) | shared | mocked |
| RPT-002 | Reports | shared | planned |
| QUOT-001 | Quotations list — the Quotations page and a lead's quotations (`GET /quotations`) | shared | in-progress |
| QUOT-002 | Quotation detail — the document as the backend prints it (`GET /quotations/{quotationId}`) | shared | in-progress |
| QUOT-003 | Open a quotation's PDF (`GET /quotations/{quotationId}/pdf`) | shared | in-progress |
| SO-001 | Sales orders list | shared | planned |
| APPR-001 | Approval inbox — amount-based escalation | shared | planned |
| CMPL-001 | Complaints list and QA review | shared | planned |
| TASK-001 | Tasks and daily planner | shared | planned |
| CHNL-001 | Channel partners list and detail | shared | planned |
| MKT-001 | Marketing offers — set by Admin, visible to channel partners only | shared | planned |
| SCHM-001 | Schemes — set by Admin, visible to everyone | shared | planned |
| MSTR-001 | Masters — products, stock, price lists, territories | shared | planned |
| MSTR-002 | Lead lookups — sources, irrigation systems, lost reasons and the territory picker (`GET /lookups/*`) | shared | in-progress |
| SUBS-001 | Subsidy forms and case status | shared | planned |
| ACCT-001 | Accounts work queue | shared | planned |
| DISP-001 | Dispatch work queue | shared | planned |
| ADMN-001 | Users, roles and approval thresholds | shared | planned |
| SITE-001 | Public website — information, Product Master, phone-number entry | shared | planned |
| NOTIF-001 | In-app notifications — bell, latest notifications and unread count | shared | mocked |
| NOTIF-002 | Mark notifications as read — one or all | shared | mocked |
| MSG-001 | Conversation list with unread counts | shared | mocked |
| MSG-002 | Messages in a conversation | shared | mocked |
| MSG-003 | Send a message, optionally linking a CRM record | shared | mocked |
| MSG-004 | Start a conversation — staff directory search | shared | mocked |
| MSG-005 | Mark a conversation as read | shared | mocked |
| REPO-001 | Changelog system — one entry per change, generated CHANGELOG.md | frontend | in-progress |
| REPO-002 | Quality gates — lint rules, git hooks, CI pipeline | frontend | in-progress |
