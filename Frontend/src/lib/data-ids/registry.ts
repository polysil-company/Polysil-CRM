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
  NOTIF: "Notifications — WhatsApp and email templates and history",
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
    title: "Phone-number sign-in",
    owner: "shared",
    status: "planned",
    notes: "Auth documents exist with the backend developer; integration is deferred.",
  },
  "AUTH-002": {
    domain: "AUTH",
    title: "Current session — user, role, channel partner type, region scope",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /me"],
  },
  "LEAD-001": {
    domain: "LEAD",
    title: "List leads with filters, sorting and pagination",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /leads"],
  },
  "LEAD-002": {
    domain: "LEAD",
    title: "Create lead",
    owner: "shared",
    status: "mocked",
    endpoints: ["POST /leads"],
  },
  "LEAD-003": {
    domain: "LEAD",
    title: "Lead detail",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /leads/{leadId}"],
  },
  "LEAD-004": {
    domain: "LEAD",
    title: "Lead counts by status — navigation badges and tabs",
    owner: "shared",
    status: "mocked",
    endpoints: ["GET /leads/summary"],
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
} as const satisfies Record<string, DataIdDefinition>;

export type DataId = keyof typeof DATA_IDS;
