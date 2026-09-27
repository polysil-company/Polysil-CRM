/**
 * Data ID registry — the shared vocabulary between frontend and backend.
 *
 * A Data ID names ONE functionality: an API operation, a screen action, or a
 * cross-cutting capability. The identical ID is used by the backend for the
 * matching endpoint, so any log line, error or bug report can be traced to a
 * single functionality on both sides in seconds.
 *
 * Where a Data ID appears:
 *  - `x-data-id` header on every API request (the backend logs it too)
 *  - every log line written through `@/lib/logger`
 *  - error references shown to users: "LEAD-001 · 3f2a9c1e-…"
 *  - test names:        describe("[LEAD-001] …")
 *  - changelog entries: `dataIds: [LEAD-001]`
 *  - branches/commits:  `feature/LEAD-001-leads-table`, `feat(LEAD-001): …`
 *
 * Rules (full version in Docs/Data-IDs.md):
 *  1. Register the ID here BEFORE writing the feature or integration.
 *  2. IDs are never reused or renumbered. Retired IDs stay, marked "deprecated".
 *  3. Format is DOMAIN-NNN, where DOMAIN is a key of `DATA_ID_DOMAINS`.
 */

export const DATA_ID_PATTERN = /^([A-Z]{2,6})-(\d{3})$/;

export const DATA_ID_DOMAINS = {
  APP: "Application shell, navigation, theming, route transitions",
  OBS: "Observability — logging, API tracing, error reporting",
  DS: "Design system — tokens and component library",
  AUTH: "Authentication, session and permissions",
  LEAD: "Lead generation and management",
  QUOT: "Quotations",
  SO: "Sales orders",
  APPR: "Approvals — amount-based auto-escalation",
  CMPL: "Complaints and QA review",
  TASK: "Tasks and daily work",
  CHNL: "Channel partners — distributor, dealer, sub-dealer",
  MKT: "Marketing and promotional offers",
  SCHM: "Schemes",
  MSTR: "Masters — products, stock, price lists, territories",
  RPT: "Reports and dashboards",
  SUBS: "Subsidy forms and case status",
  ACCT: "Accounts — payments, ledgers, financial approval queue",
  DISP: "Dispatch — stock, dispatch and delivery queue",
  ADMN: "Administration — users, roles, thresholds, handover",
  NOTIF: "Notifications — in-app bell, WhatsApp and email templates and history",
  MSG: "Messages — direct conversations between staff",
  BOT: "AI assistant",
  SITE: "Public website",
  REPO: "Repository tooling — changelog, lint rules, git hooks, CI",
} as const;

export type DataIdDomain = keyof typeof DATA_ID_DOMAINS;

/** Who implements the functionality. `shared` = frontend UI + backend endpoint. */
export type DataIdOwner = "frontend" | "backend" | "shared";

/**
 * Lifecycle of a functionality.
 * - planned:     registered, not started
 * - in-progress: being built
 * - mocked:      frontend complete against MSW mocks, waiting for the real endpoint
 * - integrated:  running against the real backend in staging
 * - deprecated:  retired; the ID must not be reused
 */
export type DataIdStatus = "planned" | "in-progress" | "mocked" | "integrated" | "deprecated";

export interface DataIdDefinition {
  readonly domain: DataIdDomain;
  readonly title: string;
  readonly owner: DataIdOwner;
  readonly status: DataIdStatus;
  /** Backend operations in `METHOD /path` form, when the functionality calls the API. */
  readonly endpoints?: readonly string[];
  readonly notes?: string;
}

export const DATA_IDS = {
  "APP-001": {
    domain: "APP",
    title: "App shell — sidebar, header, role-filtered navigation, command menu",
    owner: "frontend",
    status: "in-progress",
  },
  "APP-002": {
    domain: "APP",
    title: "Theme — light, dark and system preference",
    owner: "frontend",
    status: "in-progress",
  },
  "APP-003": {
    domain: "APP",
    title: "Route transitions, page skeletons and route-level error boundaries",
    owner: "frontend",
    status: "in-progress",
  },
  "APP-004": {
    domain: "APP",
    title: "Mock scenarios for previewing loading, empty, error and contract states",
    owner: "frontend",
    status: "in-progress",
  },
  "APP-005": {
    domain: "APP",
    title: "Collapsible desktop sidebar and page titles in the top bar",
    owner: "frontend",
    status: "in-progress",
  },
  "OBS-001": {
    domain: "OBS",
    title: "Logger utility with runtime log level",
    owner: "frontend",
    status: "in-progress",
  },
  "OBS-002": {
    domain: "OBS",
    title: "API client — request IDs, error normalisation, response contract validation",
    owner: "shared",
    status: "in-progress",
    notes: "Backend must accept x-request-id / x-data-id headers and log them.",
  },
  "DS-001": {
    domain: "DS",
    title: "Design tokens (src/styles/tokens.css) and component library",
    owner: "frontend",
    status: "in-progress",
  },
  "AUTH-001": {
    domain: "AUTH",
    title: "Mobile sign-in with a one-time code — channel partners",
    owner: "shared",
    status: "mocked",
    endpoints: ["POST /auth/otp/request", "POST /auth/otp/verify"],
    notes: "Contract: backend/docs/api/auth.md. Also owns the /api/v1 same-origin rewrite.",
  },
  "AUTH-002": {
    domain: "AUTH",
    title: "Current session — user, role, organisation unit, partner and permissions",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /auth/me"],
  },
  "AUTH-003": {
    domain: "AUTH",
    title: "Email and password sign-in — Polysil staff",
    owner: "shared",
    status: "mocked",
    endpoints: ["POST /auth/login"],
  },
  "AUTH-004": {
    domain: "AUTH",
    title: "Keep signed in — rotate the access token with the refresh cookie",
    owner: "shared",
    status: "mocked",
    endpoints: ["POST /auth/refresh"],
  },
  "AUTH-005": {
    domain: "AUTH",
    title: "Sign out",
    owner: "shared",
    status: "mocked",
    endpoints: ["POST /auth/logout"],
  },
  "AUTH-006": {
    domain: "AUTH",
    title: "Signed-in routing — sign-in redirects, return path and session end",
    owner: "frontend",
    status: "in-progress",
  },
  "LEAD-001": {
    domain: "LEAD",
    title: "List leads with filters, sorting and pagination",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /leads"],
    notes:
      "Connected to the dev API: cursor paging with include_total. The backend does not sort yet — the sort and order parameters are a request to the backend.",
  },
  "LEAD-002": {
    domain: "LEAD",
    title: "Create lead",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /leads"],
    notes: "Connected to the dev API. Duplicates are flagged on the new lead, never refused.",
  },
  "LEAD-003": {
    domain: "LEAD",
    title: "Lead detail",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /leads/{leadId}"],
    notes: "Connected to the dev API.",
  },
  "LEAD-004": {
    domain: "LEAD",
    title: "Lead stats — navigation badge and sales tab",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /leads/stats"],
    notes:
      "Connected to the dev API. An exact count, by stage and priority, with the unassigned total; the badge and the tab show the total.",
  },
  "RPT-001": {
    domain: "RPT",
    title: "Dashboard overview — KPIs, pipeline, follow-ups",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /dashboard/overview"],
  },
  "QUOT-001": {
    domain: "QUOT",
    title: "Quotations list",
    owner: "shared",
    status: "planned",
  },
  "SO-001": {
    domain: "SO",
    title: "Sales orders list",
    owner: "shared",
    status: "planned",
  },
  "APPR-001": {
    domain: "APPR",
    title: "Approval inbox — amount-based escalation",
    owner: "shared",
    status: "planned",
    notes: "Account, QA and Dispatch gates apply only to requests raised by a State Manager.",
  },
  "CMPL-001": {
    domain: "CMPL",
    title: "Complaints list and QA review",
    owner: "shared",
    status: "planned",
  },
  "TASK-001": {
    domain: "TASK",
    title: "Tasks and daily planner",
    owner: "shared",
    status: "planned",
  },
  "CHNL-001": {
    domain: "CHNL",
    title: "Channel partners list and detail",
    owner: "shared",
    status: "planned",
  },
  "MKT-001": {
    domain: "MKT",
    title: "Marketing offers — set by Admin, visible to channel partners only",
    owner: "shared",
    status: "planned",
  },
  "SCHM-001": {
    domain: "SCHM",
    title: "Schemes — set by Admin, visible to everyone",
    owner: "shared",
    status: "planned",
  },
  "MSTR-001": {
    domain: "MSTR",
    title: "Masters — products, stock, price lists, territories",
    owner: "shared",
    status: "planned",
  },
  "MSTR-002": {
    domain: "MSTR",
    title: "Lead lookups — sources, irrigation systems, lost reasons and the territory picker",
    owner: "shared",
    status: "in-progress",
    endpoints: [
      "GET /lookups/lead-sources",
      "GET /lookups/mis-systems",
      "GET /lookups/lost-reasons",
      "GET /lookups/territories",
    ],
    notes: "Admin-edited lists: the frontend never hard-codes their codes or names.",
  },
  "RPT-002": {
    domain: "RPT",
    title: "Reports",
    owner: "shared",
    status: "planned",
  },
  "SUBS-001": {
    domain: "SUBS",
    title: "Subsidy forms and case status",
    owner: "shared",
    status: "planned",
    notes: "Calculation is owned by the backend; the frontend captures and displays.",
  },
  "REPO-001": {
    domain: "REPO",
    title: "Changelog system — one entry per change, generated CHANGELOG.md",
    owner: "frontend",
    status: "in-progress",
  },
  "REPO-002": {
    domain: "REPO",
    title: "Quality gates — lint rules, git hooks, CI pipeline",
    owner: "frontend",
    status: "in-progress",
  },
  "ACCT-001": {
    domain: "ACCT",
    title: "Accounts work queue",
    owner: "shared",
    status: "planned",
  },
  "DISP-001": {
    domain: "DISP",
    title: "Dispatch work queue",
    owner: "shared",
    status: "planned",
  },
  "ADMN-001": {
    domain: "ADMN",
    title: "Users, roles and approval thresholds",
    owner: "shared",
    status: "planned",
  },
  "SITE-001": {
    domain: "SITE",
    title: "Public website — information, Product Master, phone-number entry",
    owner: "shared",
    status: "planned",
  },
  "NOTIF-001": {
    domain: "NOTIF",
    title: "In-app notifications — bell, latest notifications and unread count",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /notifications"],
    notes:
      "Proposed contract in features/notifications/api/notifications.schemas.ts, to agree with the backend. Polled every 30 s until the backend picks a push transport.",
  },
  "NOTIF-002": {
    domain: "NOTIF",
    title: "Mark notifications as read — one or all",
    owner: "shared",
    status: "mocked",
    endpoints: ["POST /notifications/read"],
  },
  "MSG-001": {
    domain: "MSG",
    title: "Conversation list with unread counts",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /conversations"],
    notes:
      "Staff only — the backend must return 403 to partner users. Proposed contract in features/messages/api/messages.schemas.ts.",
  },
  "MSG-002": {
    domain: "MSG",
    title: "Messages in a conversation",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /conversations/{conversationId}/messages"],
  },
  "MSG-003": {
    domain: "MSG",
    title: "Send a message, optionally linking a CRM record",
    owner: "shared",
    status: "mocked",
    endpoints: ["POST /conversations/{conversationId}/messages"],
  },
  "MSG-004": {
    domain: "MSG",
    title: "Start a conversation — staff directory search",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /staff-directory", "POST /conversations"],
  },
  "MSG-005": {
    domain: "MSG",
    title: "Mark a conversation as read",
    owner: "shared",
    status: "mocked",
    endpoints: ["POST /conversations/{conversationId}/read"],
  },
} as const satisfies Record<string, DataIdDefinition>;

export type DataId = keyof typeof DATA_IDS;
