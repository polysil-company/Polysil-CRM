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
    endpoints: ["GET /leads", "GET /leads/areas"],
    notes:
      "Connected to the dev API: cursor paging with include_total; sorting by customer or value since BE-001 (a sort change starts from the first page); the Area filter (state, district, taluka; at most 20) since backend #50.",
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
  "LEAD-005": {
    domain: "LEAD",
    title: "Lead timeline — the lead's history, newest first",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /leads/{leadId}/timeline"],
    notes: "Cursor-paged; includes the events of leads merged into this one.",
  },
  "LEAD-006": {
    domain: "LEAD",
    title: "Add a note to a lead",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /leads/{leadId}/notes"],
    notes: "The note becomes a timeline entry and bumps the lead's last activity.",
  },
  "LEAD-007": {
    domain: "LEAD",
    title: "Move a lead's stage — contact, qualify, mark lost, reopen",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /leads/{leadId}/transition", "POST /leads/{leadId}/reopen"],
    notes:
      "Quoted and negotiation are reached through a quotation; won needs an accepted quotation. Lost needs a lost reason.",
  },
  "LEAD-008": {
    domain: "LEAD",
    title: "Assign a lead — owner and channel partner",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /leads/{leadId}/assign", "GET /leads/assignees", "GET /lookups/partners"],
    notes:
      "Only what changed is sent. Owners come from GET /leads/assignees, which is empty for roles that may not set one; a closed lead cannot be reassigned.",
  },
  "RPT-001": {
    domain: "RPT",
    title: "Dashboard overview — KPIs, pipeline, follow-ups",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /dashboard/overview"],
    notes: "The backend's shape since BE-008: snake_case, every figure a decimal string.",
  },
  "QUOT-001": {
    domain: "QUOT",
    title: "Quotations list — the Quotations page and a lead's quotations",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /quotations"],
    notes: "Cursor paging with include_total; current versions only unless asked.",
  },
  "QUOT-002": {
    domain: "QUOT",
    title: "Quotation detail — the document as the backend prints it",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /quotations/{quotationId}"],
    notes: "Every figure comes from the backend; the screen never computes a total.",
  },
  "QUOT-003": {
    domain: "QUOT",
    title: "Open a quotation's PDF",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /quotations/{quotationId}/pdf"],
    notes: "A signed URL valid for ten minutes, opened in a new tab; never fetched with the token.",
  },
  "QUOT-004": {
    domain: "QUOT",
    title: "Quotation builder — create and edit a draft",
    owner: "shared",
    status: "in-progress",
    endpoints: [
      "POST /quotations",
      "PATCH /quotations/{quotationId}",
      "PUT /quotations/{quotationId}/lines",
    ],
    notes:
      "Saves what the preview priced; 409 rate_changed names the lines whose rate or slab moved, and the builder re-prices.",
  },
  "QUOT-005": {
    domain: "QUOT",
    title: "Live pricing — the quotation preview",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /pricing/quote-lines"],
    notes: "Stores nothing; called on every change, debounced. Every printed figure comes back.",
  },
  "QUOT-006": {
    domain: "QUOT",
    title: "Send a quotation — number it, share the link, render the PDF",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /quotations/{quotationId}/send"],
    notes:
      "Sends only when discount.send_gate allows; WhatsApp waits for the PDF. The lead moves to quoted.",
  },
  "QUOT-007": {
    domain: "QUOT",
    title: "Ask a manager to approve a quotation's discount",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /quotations/{quotationId}/request-approval"],
    notes: "Any save or delete of the draft cancels a pending request.",
  },
  "QUOT-008": {
    domain: "QUOT",
    title: "Record the customer's answer — accepted, rejected or negotiation",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /quotations/{quotationId}/transition"],
    notes: "Accepted moves the lead to won, negotiation to negotiation; rejected moves nothing.",
  },
  "QUOT-009": {
    domain: "QUOT",
    title: "Revise a quotation, and its versions",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /quotations/{quotationId}/revise", "GET /quotations/{quotationId}/versions"],
    notes: "A new draft of the same number at today's prices; one open revision per number.",
  },
  "QUOT-010": {
    domain: "QUOT",
    title: "A quotation's history",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /quotations/{quotationId}/timeline"],
  },
  "QUOT-011": {
    domain: "QUOT",
    title: "Delete a draft quotation",
    owner: "shared",
    status: "in-progress",
    endpoints: ["DELETE /quotations/{quotationId}"],
    notes: "Drafts only, with quotations.delete. A sent quotation is never deleted.",
  },
  "QUOT-012": {
    domain: "QUOT",
    title: "The customer's quotation page — /q/{token}",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /public/q/{token}", "GET /public/q/{token}/pdf"],
    notes:
      "No sign-in. Shows the number, seller, validity and total only; the PDF opens from the button, never on load, so a link preview is not a view.",
  },
  "SO-001": {
    domain: "SO",
    title: "Sales orders list",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /orders"],
    notes:
      "Cursor paging with include_total; each row carries dispatched_pct and approval_waiting_on.",
  },
  "SO-002": {
    domain: "SO",
    title: "A sales order — the document, its approval chain, PDF and history",
    owner: "shared",
    status: "in-progress",
    endpoints: [
      "GET /orders/{orderId}",
      "GET /orders/{orderId}/pdf",
      "GET /orders/{orderId}/timeline",
    ],
    notes: "Every figure comes from the backend. Blocks the caller may not see come back null.",
  },
  "SO-003": {
    domain: "SO",
    title: "New order from accepted quotations, and a draft's header",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /orders", "PATCH /orders/{orderId}", "DELETE /orders/{orderId}"],
    notes:
      "Quotations must agree on partner, place of supply, seller, price date, office and territory.",
  },
  "SO-004": {
    domain: "SO",
    title: "Submit an order for approval, and cancel it",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /orders/{orderId}/submit", "POST /orders/{orderId}/cancel"],
    notes:
      "Submit numbers the order and builds the chain by value: managers, then Accounts, then Dispatch.",
  },
  "SO-005": {
    domain: "SO",
    title: "A direct order typed in line by line, and a draft's lines",
    owner: "shared",
    status: "planned",
    endpoints: ["POST /orders", "PUT /orders/{orderId}/lines", "POST /pricing/quote-lines"],
    notes:
      "Party, place of supply and lines as on a quotation, priced by the backend; a lead is optional.",
  },
  "APPR-001": {
    domain: "APPR",
    title: "Approval inbox — amount-based escalation",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /approvals/pending", "POST /approvals/steps/{stepId}/decision"],
    notes:
      "Quotation discounts and sales orders side by side, with the asker's reason (request_remark, backend #49). An order's chain is its managers by value, then Accounts, then Dispatch.",
  },
  "APPR-002": {
    domain: "APPR",
    title: "Approval limits — order value and discount per role",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /approvals/thresholds", "PUT /approvals/thresholds"],
    notes:
      "Anyone signed in reads them; masters.edit changes them. Each level stays above the one below.",
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
  "MSTR-003": {
    domain: "MSTR",
    title: "Product picker — search the catalogue",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /products"],
    notes:
      "Active products by description; the rate is not here — it comes from the pricing preview.",
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
  "DISP-002": {
    domain: "DISP",
    title: "Record a dispatch on an order, void it, close the rest short",
    owner: "shared",
    status: "in-progress",
    endpoints: [
      "POST /orders/{orderId}/dispatches",
      "POST /dispatches/{dispatchId}/void",
      "POST /orders/{orderId}/close-short",
    ],
    notes:
      "Line by line, at most the open quantity, in the unit's precision; the system records invoices, never issues them.",
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
    status: "in-progress",
    endpoints: ["GET /notifications"],
    notes:
      "Served since BE-009 (backend/docs/api/notifications.md). The badge polls ?limit=1 every 30 s; the list is read when the bell opens. No push.",
  },
  "NOTIF-002": {
    domain: "NOTIF",
    title: "Mark notifications as read — one or all",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /notifications/read"],
  },
  "MSG-001": {
    domain: "MSG",
    title: "Conversation list with unread counts",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /conversations"],
    notes:
      "Served since BE-010 (backend/docs/api/messages.md). Staff only: partner users get 403. A conversation is listed once someone writes in it.",
  },
  "MSG-002": {
    domain: "MSG",
    title: "Messages in a conversation",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /conversations/{conversationId}/messages"],
  },
  "MSG-003": {
    domain: "MSG",
    title: "Send a message, optionally linking a CRM record",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /conversations/{conversationId}/messages"],
  },
  "MSG-004": {
    domain: "MSG",
    title: "Start a conversation — staff directory search",
    owner: "shared",
    status: "in-progress",
    endpoints: ["GET /staff-directory", "POST /conversations"],
  },
  "MSG-005": {
    domain: "MSG",
    title: "Mark a conversation as read",
    owner: "shared",
    status: "in-progress",
    endpoints: ["POST /conversations/{conversationId}/read"],
  },
} as const satisfies Record<string, DataIdDefinition>;

export type DataId = keyof typeof DATA_IDS;
