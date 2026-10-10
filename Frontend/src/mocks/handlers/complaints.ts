import { http, HttpResponse } from "msw";

import {
  COMPLAINT_STATUSES,
  checkRequestSchema,
  cancelComplaintRequestSchema,
  createComplaintRequestSchema,
  patchComplaintRequestSchema,
  qcRequestSchema,
  replaceLinesRequestSchema,
  type ComplaintPageWire,
  type ComplaintStatus,
  type ComplaintStatsWire,
  type ComplaintWire,
  type CreateComplaintRequest,
  COMPLAINT_ATTACHMENT_MAX_BYTES,
  COMPLAINT_ATTACHMENT_TYPES,
  COMPLAINT_ATTACHMENTS_MAX,
  ATTACHMENT_KINDS,
  createSlaPolicyRequestSchema,
  remedyRequestSchema,
  withdrawRemedyRequestSchema,
  type SlaPolicyWire,
  type PatchComplaintRequest,
} from "@/features/complaints/api/complaints.schemas";
import type { TimelineEventWire, TimelinePageWire } from "@/features/leads/api/leads.schemas";
import { summarizeSchemaIssues } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import type { Role } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { refundManagersFor, type MockApprovalStep } from "@/mocks/data/approvals";
import { slaFor, type MockComplaint } from "@/mocks/data/complaints";
import { mockLookupRows } from "@/mocks/data/lookups";
import { chainSteps } from "@/mocks/data/orders";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { MOCK_ID_SPACE, MOCK_PARTNERS, MOCK_STAFF, mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { findMockTerritory } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 100;
const MANAGER_ROLES = new Set(["district_manager", "state_manager", "regional_manager", "admin"]);
const QC_ROLES = new Set(["qa_manager", "admin"]);

interface Caller {
  readonly role: string;
  readonly user: { id: string; full_name: string };
  readonly create: boolean;
  readonly view: boolean;
}

function caller(): Caller {
  const role = readMockRole();
  const permissions = mockPermissionsFor(role);
  const me = mockMeFor(role).data;
  return {
    role,
    user: { id: me.id, full_name: me.full_name },
    create: can(permissions, "complaints", "create"),
    view: can(permissions, "complaints", "view"),
  };
}

/** What this caller may do on this complaint, as the backend's `can` says. */
function canFor(complaint: MockComplaint, who: Caller): ComplaintWire["can"] {
  const draft = complaint.status === "draft";
  return {
    edit: draft && who.create,
    submit: draft && who.create,
    delete: draft && who.create && complaint.submit_count === 0,
    cancel: (draft || complaint.status === "submitted") && who.create,
    check: complaint.status === "submitted" && MANAGER_ROLES.has(who.role),
    qc: complaint.status === "under_qc" && QC_ROLES.has(who.role),
    upload:
      ((draft || complaint.status === "submitted") && who.create) ||
      (complaint.status === "under_qc" && QC_ROLES.has(who.role)),
    remedy: complaint.status === "qc_approved" && QC_ROLES.has(who.role),
    withdraw:
      complaint.status === "remedy_pending" &&
      complaint.remedy?.status === "pending" &&
      QC_ROLES.has(who.role),
  };
}

function toWire(complaint: MockComplaint, who: Caller = caller()): ComplaintWire {
  return { ...complaint, can: canFor(complaint, who) };
}

function fieldsOf(error: Parameters<typeof summarizeSchemaIssues>[0]): Record<string, string> {
  return Object.fromEntries(
    summarizeSchemaIssues(error).map((issue) => [issue.path, issue.message]),
  );
}

function invalid(fields: Record<string, string>, code = "validation_error"): Response {
  return errorResponse(422, code, "Some fields need correcting.", fields);
}

function findComplaint(complaintId: unknown): MockComplaint | Response {
  const who = caller();
  if (!who.view) return errorResponse(403, "forbidden", "Complaints are not in your permissions.");
  return (
    mockDb.complaints.find((item) => item.id === complaintId) ??
    errorResponse(404, "not_found", "No such complaint.")
  );
}

function save(next: MockComplaint): void {
  mockDb.complaints = mockDb.complaints.map((item) => (item.id === next.id ? next : item));
}

function record(
  complaint: MockComplaint,
  kind: string,
  payload: Record<string, unknown> = {},
): void {
  const who = caller();
  const events = mockDb.complaintEvents.get(complaint.id) ?? seedEvents(complaint);
  mockDb.writtenEvents += 1;
  const event: TimelineEventWire = {
    id: mockUuid(MOCK_ID_SPACE.timeline, 0x50000 + mockDb.writtenEvents),
    kind,
    occurred_at: new Date().toISOString(),
    actor: who.user,
    payload,
  };
  mockDb.complaintEvents.set(complaint.id, [event, ...events]);
}

/** The history the seed implies: raised, submitted, checked, QC, cancelled. Newest first. */
function seedEvents(complaint: MockComplaint): TimelineEventWire[] {
  const events: TimelineEventWire[] = [];
  const push = (
    kind: string,
    at: string,
    actor: MockComplaint["raised_by"],
    payload = {},
  ): void => {
    events.push({
      id: mockUuid(
        MOCK_ID_SPACE.timeline,
        0x40000 + events.length + Number.parseInt(complaint.id.slice(-4), 16) * 10,
      ),
      kind,
      occurred_at: at,
      actor,
      payload,
    });
  };
  push("complaint.created", complaint.created_at, complaint.raised_by);
  if (complaint.submitted_at !== null) {
    push("complaint.submitted", complaint.submitted_at, complaint.raised_by, {
      complaint_no: complaint.complaint_no,
    });
  }
  if (complaint.check !== null) {
    push(
      complaint.check.decision === "approve" ? "complaint.approved" : "complaint.returned",
      complaint.check.at,
      complaint.check.by,
      { remark: complaint.check.remark },
    );
  }
  if (complaint.quality !== null) {
    push(`complaint.qc_${complaint.quality.verdict}`, complaint.quality.at, complaint.quality.by, {
      remark: complaint.quality.remark,
    });
  }
  if (complaint.cancellation) {
    push("complaint.cancelled", complaint.cancellation.at, complaint.cancellation.by, {
      reason: complaint.cancellation.reason,
    });
  }
  return events.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
}

/** Replays a write made with the same Idempotency-Key, or refuses the key for another request. */
function replay(request: Request, serialized: string): Response | string {
  const key = request.headers.get("idempotency-key");
  if (key === null)
    return errorResponse(400, "idempotency_key_required", "Idempotency-Key missing.");
  const earlier = mockDb.complaintWrites.get(key);
  if (earlier === undefined) return key;
  if (earlier.body !== serialized) {
    return errorResponse(
      409,
      "idempotency_key_reused",
      "This Idempotency-Key was already used for a different request.",
    );
  }
  const complaint = mockDb.complaints.find((item) => item.id === earlier.complaintId);
  return complaint === undefined ? key : HttpResponse.json({ data: toWire(complaint) });
}

function remember(key: string, serialized: string, complaint: MockComplaint): void {
  mockDb.complaintWrites.set(key, { body: serialized, complaintId: complaint.id });
}

type LineIn = CreateComplaintRequest["lines"][number];

/** A value, or the field errors that refuse it. */
type Checked<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly fields: Record<string, string> };

let lineSerial = 0;

/** The lines rules: each product once, supplied above zero, defective not above supplied. */
function linesOf(lines: readonly LineIn[]): Checked<MockComplaint["lines"]> {
  const fields: Record<string, string> = {};
  const seen = new Set<string>();
  const out = lines.map((line, index) => {
    const product = MOCK_PRODUCTS.find((item) => item.id === line.product_id);
    const supplied = Number(line.supplied_qty);
    const defective = Number(line.defective_qty);
    if (product === undefined) fields[`lines.${String(index)}.product_id`] = "no such product";
    if (seen.has(line.product_id))
      fields[`lines.${String(index)}.product_id`] = "each product once";
    seen.add(line.product_id);
    if (!(supplied > 0)) fields[`lines.${String(index)}.supplied_qty`] = "more than zero";
    if (!(defective >= 0)) fields[`lines.${String(index)}.defective_qty`] = "zero or more";
    else if (defective > supplied)
      fields[`lines.${String(index)}.defective_qty`] = "not more than supplied";
    return {
      id: mockUuid(MOCK_ID_SPACE.complaint, 0x5000 + (lineSerial += 1)),
      product: { id: line.product_id, description: product?.name ?? null },
      uom: product?.uom ?? null,
      supplied_qty: line.supplied_qty,
      defective_qty: line.defective_qty,
      failure_frequency: line.failure_frequency?.trim() || null,
      remark: line.remark?.trim() || null,
    };
  });
  return Object.keys(fields).length > 0 ? { ok: false, fields } : { ok: true, value: out };
}

type HeaderIn = PatchComplaintRequest;

/** The header fields a create or a patch sets, with their links resolved. */
function headerOf(body: HeaderIn, base: MockComplaint | null): Checked<Partial<MockComplaint>> {
  const fields: Record<string, string> = {};
  const today = todayInIndia();
  const next: Partial<MockComplaint> = {};
  if (body.description !== undefined) next.description = body.description.trim();
  if (body.contact_name !== undefined) next.contact_name = body.contact_name.trim();
  if (body.contact_mobile !== undefined) {
    const digits = body.contact_mobile.replace(/\D/g, "").slice(-10);
    if (!/^[6-9]\d{9}$/.test(digits)) fields.contact_mobile = "an Indian mobile number";
    next.contact_mobile = `+91${digits}`;
  }
  if (body.territory_id !== undefined) {
    const territory = findMockTerritory(body.territory_id);
    if (territory === undefined) fields.territory_id = "no such territory";
    else next.territory = { id: territory.id, name: territory.name };
  }
  if (body.complaint_type_id !== undefined) {
    const type = mockLookupRows("complaint-types").find((row) => row.id === body.complaint_type_id);
    if (type === undefined) fields.complaint_type_id = "no such type";
    else next.complaint_type = { id: type.id, code: type.code, name: type.name };
  }
  if (body.severity !== undefined) next.severity = body.severity;
  if (body.partner_id !== undefined) {
    const partner = MOCK_PARTNERS.find((item) => item.id === body.partner_id);
    next.partner =
      partner === undefined
        ? null
        : { id: partner.id, hidden: false, name: partner.name, partner_type: partner.partner_type };
  }
  if (body.lead_id !== undefined) {
    const lead = mockDb.leads.find((item) => item.id === body.lead_id);
    next.lead =
      lead === undefined
        ? null
        : {
            id: lead.id,
            hidden: false,
            inquiry_no: lead.inquiry_no,
            farmer_name: lead.farmer_name,
          };
  }
  if (body.sales_order_id !== undefined) {
    const order = mockDb.orders.find((item) => item.id === body.sales_order_id);
    next.sales_order =
      order === undefined ? null : { id: order.id, hidden: false, order_no: order.order_no };
    // Linking an order fills the challan and supply date from its latest dispatch.
    const latest = order?.dispatches.at(-1);
    if (latest !== undefined) {
      if (body.dc_no == null && (base?.dc_no ?? null) === null) next.dc_no = latest.dc_no;
      if (body.supply_date == null && (base?.supply_date ?? null) === null)
        next.supply_date = latest.dc_date ?? latest.dispatched_at.slice(0, 10);
    }
  }
  for (const key of ["dc_no", "reg_no", "pims_no", "sample_courier_detail"] as const) {
    const value = body[key];
    if (value !== undefined) next[key] = value?.trim() || null;
  }
  for (const key of ["supply_date", "sample_courier_date"] as const) {
    const value = body[key];
    if (value !== undefined) {
      if (value !== null && value > today) fields[key] = "cannot be after today";
      next[key] = value;
    }
  }
  return Object.keys(fields).length > 0 ? { ok: false, fields } : { ok: true, value: next };
}

function isStatus(value: string): value is ComplaintStatus {
  return COMPLAINT_STATUSES.some((status) => status === value);
}

function moved(): Response {
  return errorResponse(409, "status_changed", "The complaint moved on; reload it.");
}

function complaintPath(rest = ""): string {
  return buildApiUrl(`/complaints/:complaintId${rest}`);
}

/** The uploaded file as a link; a stand-in where the runtime can't make one (jsdom). */
function objectUrlOf(file: Blob): string {
  try {
    return URL.createObjectURL(file);
  } catch {
    return "/icon.svg";
  }
}

type MockRemedy = NonNullable<MockComplaint["remedy"]>;
type MockApproval = NonNullable<NonNullable<MockRemedy["refund"]>["approval"]>;

let remedySerial = 0;

/** The seeded QC officer, as in mocks/data/complaints. */
const MOCK_QC = MOCK_STAFF[4];

/** The refund's next undecided step, as a row of the approvals inbox. */
function refundQueueStep(complaint: MockComplaint): MockApprovalStep | null {
  const approval = complaint.remedy?.refund?.approval;
  const next = approval?.steps.find((step) => (step.decision ?? null) === null);
  if (approval == null || next === undefined) return null;
  const previous = approval.steps.filter((step) => step.seq < next.seq).at(-1);
  return {
    stepId: next.id,
    requestId: approval.request_id,
    seq: next.seq,
    role: next.role,
    stalled: false,
    docType: "complaint",
    docId: complaint.id,
    number: complaint.complaint_no,
    partyName: complaint.contact_name,
    total: complaint.remedy?.refund?.amount ?? "0.00",
    isProvisional: false,
    discountPct: null,
    requestRemark: complaint.remedy?.remark ?? null,
    // Every mock role signs in as one user, so the seeded QC officer stands in as the asker;
    // otherwise the manager deciding it would be refused as deciding their own request.
    raisedBy: MOCK_QC === undefined ? null : { id: MOCK_QC.id, full_name: MOCK_QC.full_name },
    raisedAt: previous?.decided_at ?? complaint.remedy?.chosen_at ?? complaint.updated_at,
    decision: null,
    remark: null,
    decidedAt: null,
    closed: null,
  };
}

function closeRefundRows(complaint: MockComplaint): void {
  const requestId = complaint.remedy?.refund?.approval?.request_id;
  for (const step of mockDb.approvalSteps) {
    if (step.requestId === requestId && step.decision === null) step.closed = "deleted";
  }
}

/**
 * APPR-001, CMPL-007 · A decision on a refund's step from the approvals inbox: the managers in
 * turn, then Accounts, whose remark is the payment reference; the last approval closes the
 * complaint. A rejection sends it back to QC to choose again.
 */
export function decideComplaintRefundStep(
  complaintId: string,
  stepId: string,
  decision: "approve" | "reject",
  remark: string | null,
  role: Role,
): ComplaintWire | null {
  const complaint = mockDb.complaints.find((item) => item.id === complaintId);
  const refund = complaint?.remedy?.refund;
  if (
    complaint === undefined ||
    complaint.remedy == null ||
    refund == null ||
    refund.approval == null
  ) {
    return null;
  }
  const me = mockMeFor(role).data;
  const now = new Date().toISOString();
  const steps = refund.approval.steps.map((step) =>
    step.id === stepId
      ? {
          ...step,
          decision,
          by: { id: me.id, full_name: me.full_name },
          remark,
          decided_at: now,
          decided_role: null,
        }
      : step,
  );
  const decided = steps.find((step) => step.id === stepId);
  const last = steps.every((step) => step.decision === "approve");
  const approval: MockApproval = {
    ...refund.approval,
    steps,
    status: decision === "reject" ? "rejected" : last ? "approved" : "pending",
  };
  const remedy: MockRemedy = {
    ...complaint.remedy,
    status: decision === "reject" ? "rejected" : last ? "completed" : "pending",
    completed_at: last && decision === "approve" ? now : null,
    refund: {
      ...refund,
      approval,
      payment_reference:
        last && decision === "approve" && decided?.role === "account_manager" ? remark : null,
    },
  };
  const next: MockComplaint = {
    ...complaint,
    remedy,
    status: decision === "reject" ? "qc_approved" : last ? "closed" : "remedy_pending",
    closed_at: last && decision === "approve" ? now : null,
    updated_at: now,
  };
  save(next);
  // The backend writes an event at the end of the chain only: paid, or not approved.
  if (decision === "reject") {
    record(next, "complaint.refund_rejected", { amount: refund.amount });
  } else if (last) {
    record(next, "complaint.refund_paid", { amount: refund.amount });
    record(next, "complaint.closed", {});
  }
  if (decision === "approve" && !last) {
    const step = refundQueueStep(next);
    if (step !== null) mockDb.approvalSteps.push(step);
  }
  return toWire(next);
}

export const complaintHandlers = [
  /** CMPL-001 · Newest first; `awaiting=me` is the user's queue, oldest first. */
  http.get(buildApiUrl("/complaints"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    if (!who.view)
      return errorResponse(403, "forbidden", "Complaints are not in your permissions.");

    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT),
    );
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : decodeCursor(cursor);
    if (offset === null) return invalid({ cursor: "malformed cursor" });
    const statuses = url.searchParams
      .getAll("status")
      .flatMap((value) => value.split(","))
      .filter(isStatus);
    const severity = url.searchParams.get("severity");
    const typeId = url.searchParams.get("complaint_type_id");
    const leadId = url.searchParams.get("lead_id");
    const orderId = url.searchParams.get("sales_order_id");
    const owner = url.searchParams.get("owner");
    const breached = url.searchParams.get("breached") === "true";
    const awaitingMe = url.searchParams.get("awaiting") === "me";
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();

    let matches =
      scenario === "empty"
        ? []
        : mockDb.complaints.filter((complaint) => {
            const can = canFor(complaint, who);
            return (
              (statuses.length === 0 || statuses.includes(complaint.status)) &&
              (severity === null || complaint.severity === severity) &&
              (typeId === null || complaint.complaint_type.id === typeId) &&
              (leadId === null || complaint.lead?.id === leadId) &&
              (orderId === null || complaint.sales_order?.id === orderId) &&
              (owner !== "none" || complaint.owner === null) &&
              (!breached ||
                complaint.sla?.response_breached === true ||
                complaint.sla?.resolution_breached === true) &&
              (!awaitingMe || can.check || can.qc) &&
              (q === "" ||
                (complaint.complaint_no ?? "").toLowerCase().includes(q) ||
                complaint.contact_name.toLowerCase().includes(q) ||
                complaint.contact_mobile.includes(q.replace(/\D/g, "") || "\u0000"))
            );
          });
    matches = awaitingMe
      ? [...matches].sort((a, b) => (a.submitted_at ?? "").localeCompare(b.submitted_at ?? ""))
      : [...matches].sort((a, b) => b.created_at.localeCompare(a.created_at));
    const counted = url.searchParams.get("include_total") === "true";
    const body: ComplaintPageWire = {
      data: matches.slice(offset, offset + limit).map((complaint) => ({
        id: complaint.id,
        complaint_no: complaint.complaint_no,
        status: complaint.status,
        complaint_type: complaint.complaint_type,
        severity: complaint.severity,
        contact_name: complaint.contact_name,
        partner: complaint.partner,
        owner: complaint.owner,
        first_submitted_at: complaint.submitted_at,
        breached:
          complaint.sla?.response_breached === true || complaint.sla?.resolution_breached === true,
        created_at: complaint.created_at,
      })),
      meta: {
        limit,
        next_cursor: offset + limit < matches.length ? encodeCursor(offset + limit) : null,
        total: counted ? matches.length : null,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/complaints/stats"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const rows = scenario === "empty" ? [] : mockDb.complaints;
    const byStatus = Object.fromEntries(
      COMPLAINT_STATUSES.map((status) => [
        status,
        rows.filter((row) => row.status === status).length,
      ]),
    );
    const body: ComplaintStatsWire = {
      data: {
        by_status: byStatus,
        breached: rows.filter(
          (row) => row.sla?.response_breached === true || row.sla?.resolution_breached === true,
        ).length,
        no_target: rows.filter((row) => row.sla?.policy === "none").length,
        storage_available: true,
      },
    };
    return HttpResponse.json(body);
  }),

  /** CMPL-003 · A draft: the type, the contact, where it is installed, and 1 to 20 products. */
  http.post(buildApiUrl("/complaints"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const who = caller();
    if (!who.create) return errorResponse(403, "forbidden", "You may not raise complaints.");
    const raw: unknown = await request.json();
    const serialized = JSON.stringify(raw);
    const key = replay(request, serialized);
    if (key instanceof Response) return key;

    const parsed = createComplaintRequestSchema.safeParse(raw);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const { lines: linesIn, ...headerIn } = parsed.data;
    const lines = linesOf(linesIn);
    if (!lines.ok) return invalid(lines.fields);
    const header = headerOf(headerIn, null);
    if (!header.ok) return invalid(header.fields);
    const now = new Date().toISOString();
    const complaint: MockComplaint = {
      id: mockUuid(
        MOCK_ID_SPACE.complaint,
        0x100 + mockDb.complaints.length + mockDb.complaintWrites.size,
      ),
      complaint_no: null,
      status: "draft",
      complaint_type: { id: "", code: "", name: "" },
      severity: "medium",
      description: "",
      contact_name: "",
      contact_mobile: "",
      territory: { id: "", name: "" },
      partner: null,
      lead: null,
      sales_order: null,
      dc_no: null,
      supply_date: null,
      reg_no: null,
      pims_no: null,
      sample_courier_date: null,
      sample_courier_detail: null,
      attachments: [],
      check: null,
      quality: null,
      cancellation: null,
      sla: null,
      submit_count: 0,
      owner: null,
      owner_org_unit: { id: "ou-vadodara", name: "Vadodara District" },
      raised_by: who.user,
      remedy: null,
      closed_at: null,
      created_at: now,
      updated_at: now,
      submitted_at: null,
      ...header.value,
      lines: lines.value,
    };
    mockDb.complaints = [complaint, ...mockDb.complaints];
    remember(key, serialized, complaint);
    // Its history starts from the seed rule: "complaint.created" at created_at.
    mockDb.complaintEvents.set(complaint.id, seedEvents(complaint));
    return HttpResponse.json({ data: toWire(complaint) }, { status: 201 });
  }),

  /** CMPL-009 · The list as a file, with the same filters. Before /complaints/:id. */
  http.get(buildApiUrl("/complaints/export"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const lines = [
      "Number\tStatus\tSeverity\tContact\tType",
      ...mockDb.complaints.map((item) =>
        [
          item.complaint_no ?? "Draft",
          item.status,
          item.severity,
          item.contact_name,
          item.complaint_type.name,
        ].join("\t"),
      ),
    ];
    return new HttpResponse(lines.join("\n"), {
      headers: {
        "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content-disposition": `attachment; filename="complaints-${todayInIndia()}.xlsx"`,
      },
    });
  }),

  http.get(complaintPath(), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const complaint = findComplaint(params.complaintId);
    return complaint instanceof Response
      ? complaint
      : HttpResponse.json({ data: toWire(complaint) });
  }),

  http.get(complaintPath("/timeline"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    const events = mockDb.complaintEvents.get(complaint.id) ?? seedEvents(complaint);
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get("limit") ?? 20) || 20;
    const offset = decodeCursor(url.searchParams.get("cursor") ?? encodeCursor(0)) ?? 0;
    const body: TimelinePageWire = {
      data: events.slice(offset, offset + limit),
      meta: {
        limit,
        next_cursor: offset + limit < events.length ? encodeCursor(offset + limit) : null,
      },
    };
    return HttpResponse.json(body);
  }),

  /** CMPL-003 · A draft's header. */
  http.patch(complaintPath(), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ id: params.complaintId, raw });
    const key = replay(request, serialized);
    if (key instanceof Response) return key;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    if (complaint.status !== "draft") {
      return errorResponse(409, "complaint_not_draft", "The complaint is no longer a draft.");
    }
    const parsed = patchComplaintRequestSchema.safeParse(raw);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const header = headerOf(parsed.data, complaint);
    if (!header.ok) return invalid(header.fields);
    const next: MockComplaint = {
      ...complaint,
      ...header.value,
      updated_at: new Date().toISOString(),
    };
    save(next);
    remember(key, serialized, next);
    return HttpResponse.json({ data: toWire(next) });
  }),

  /** CMPL-003 · A draft's products, 1 to 20. */
  http.put(complaintPath("/lines"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ id: params.complaintId, raw });
    const key = replay(request, serialized);
    if (key instanceof Response) return key;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    if (complaint.status !== "draft") {
      return errorResponse(409, "complaint_not_draft", "The complaint is no longer a draft.");
    }
    const parsed = replaceLinesRequestSchema.safeParse(raw);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const lines = linesOf(parsed.data.lines);
    if (!lines.ok) return invalid(lines.fields);
    const next: MockComplaint = {
      ...complaint,
      lines: lines.value,
      updated_at: new Date().toISOString(),
    };
    save(next);
    remember(key, serialized, next);
    return HttpResponse.json({ data: toWire(next) });
  }),

  /** CMPL-003 · A draft never submitted. */
  http.delete(complaintPath(), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    if (complaint.status !== "draft" || complaint.submit_count > 0) {
      return errorResponse(
        409,
        "complaint_not_draft",
        "A submitted complaint is cancelled, not deleted.",
      );
    }
    mockDb.complaints = mockDb.complaints.filter((item) => item.id !== complaint.id);
    return new HttpResponse(null, { status: 204 });
  }),

  /** CMPL-003 · Submit: the challan and supply date are needed, and something defective. */
  http.post(complaintPath("/submit"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const serialized = JSON.stringify({ id: params.complaintId, submit: true });
    const key = replay(request, serialized);
    if (key instanceof Response) return key;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    if (complaint.status !== "draft") return moved();
    const missing: Record<string, string> = {};
    if (complaint.dc_no === null) missing.dc_no = "needed to submit";
    if (complaint.supply_date === null) missing.supply_date = "needed to submit";
    if (Object.keys(missing).length > 0) {
      return errorResponse(422, "missing_for_submit", "Fill these in before submitting.", missing);
    }
    if (complaint.lines.every((line) => Number(line.defective_qty) === 0)) {
      return errorResponse(422, "nothing_defective", "Nothing is marked defective.", {
        lines: "nothing defective",
      });
    }
    const now = Date.now();
    const serial = mockDb.complaints.filter((item) => item.complaint_no !== null).length + 1;
    const next: MockComplaint = {
      ...complaint,
      status: "submitted",
      complaint_no:
        complaint.complaint_no ?? `Poly/Comp./2026-27/GJ/${String(serial).padStart(2, "0")}`,
      submit_count: complaint.submit_count + 1,
      check: null,
      sla: slaFor(complaint.severity, now, null, null, now),
      submitted_at: new Date(now).toISOString(),
      updated_at: new Date(now).toISOString(),
    };
    save(next);
    remember(key, serialized, next);
    record(next, "complaint.submitted", { complaint_no: next.complaint_no });
    return HttpResponse.json({ data: toWire(next) });
  }),

  /** CMPL-004 · Approve (to QC, with a severity and an owner) or return (to the raiser). */
  http.post(complaintPath("/check"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ id: params.complaintId, raw });
    const key = replay(request, serialized);
    if (key instanceof Response) return key;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    const parsed = checkRequestSchema.safeParse(raw);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    if (complaint.status !== "submitted") return moved();
    const who = caller();
    if (!MANAGER_ROLES.has(who.role)) {
      return errorResponse(403, "forbidden", "This is not yours to do on this complaint.");
    }
    const body = parsed.data;
    const approve = body.decision === "approve";
    if (!approve && (body.severity != null || body.owner_user_id != null)) {
      return invalid({ severity: "with approve only" });
    }
    const owner =
      body.owner_user_id == null
        ? complaint.owner
        : MOCK_STAFF.find((person) => person.id === body.owner_user_id);
    if (owner === undefined) return invalid({ owner_user_id: "not one of the assignees" });
    const now = new Date();
    const next: MockComplaint = {
      ...complaint,
      status: approve ? "under_qc" : "draft",
      severity: approve ? (body.severity ?? complaint.severity) : complaint.severity,
      owner: approve ? owner : complaint.owner,
      check: {
        decision: body.decision,
        remark: body.remark.trim(),
        by: who.user,
        at: now.toISOString(),
        internal_note: body.internal_note?.trim() || null,
      },
      sla:
        complaint.sla === null
          ? null
          : { ...complaint.sla, responded_at: complaint.sla.responded_at ?? now.toISOString() },
      updated_at: now.toISOString(),
    };
    save(next);
    remember(key, serialized, next);
    record(next, approve ? "complaint.approved" : "complaint.returned", { remark: body.remark });
    return HttpResponse.json({ data: toWire(next) });
  }),

  http.get(complaintPath("/assignees"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    return HttpResponse.json({
      data: MOCK_STAFF.map((person) => ({ ...person, org_unit_id: null })),
    });
  }),

  /** CMPL-005 · The QC verdict, with the sample's dates (none after today). */
  http.post(complaintPath("/qc"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ id: params.complaintId, raw });
    const key = replay(request, serialized);
    if (key instanceof Response) return key;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    const parsed = qcRequestSchema.safeParse(raw);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    if (complaint.status !== "under_qc") return moved();
    const who = caller();
    if (!QC_ROLES.has(who.role)) {
      return errorResponse(403, "forbidden", "This is not yours to do on this complaint.");
    }
    const body = parsed.data;
    const today = todayInIndia();
    const late: Record<string, string> = {};
    for (const field of ["sample_received_on", "tested_on", "field_visit_on"] as const) {
      const value = body[field];
      if (value != null && value > today) late[field] = "cannot be after today";
      if (
        field === "sample_received_on" &&
        value != null &&
        complaint.supply_date !== null &&
        value < complaint.supply_date
      ) {
        late[field] = "not before the supply date";
      }
    }
    if (Object.keys(late).length > 0) return invalid(late);
    const now = new Date();
    const next: MockComplaint = {
      ...complaint,
      status: body.verdict === "approved" ? "qc_approved" : "qc_rejected",
      quality: {
        verdict: body.verdict,
        remark: body.remark.trim(),
        sample_received_on: body.sample_received_on ?? null,
        tested_on: body.tested_on ?? null,
        field_visit_on: body.field_visit_on ?? null,
        by: who.user,
        at: now.toISOString(),
        internal_note: body.internal_note?.trim() || null,
      },
      sla: complaint.sla === null ? null : { ...complaint.sla, resolved_at: now.toISOString() },
      updated_at: now.toISOString(),
    };
    save(next);
    remember(key, serialized, next);
    record(next, `complaint.qc_${body.verdict}`, { remark: body.remark });
    return HttpResponse.json({ data: toWire(next) });
  }),

  /** CMPL-003 · Cancel a draft or a submitted complaint, with a reason. */
  http.post(complaintPath("/cancel"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ id: params.complaintId, raw });
    const key = replay(request, serialized);
    if (key instanceof Response) return key;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    const parsed = cancelComplaintRequestSchema.safeParse(raw);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    if (complaint.status !== "draft" && complaint.status !== "submitted") return moved();
    const who = caller();
    const now = new Date().toISOString();
    const next: MockComplaint = {
      ...complaint,
      status: "cancelled",
      cancellation: { reason: parsed.data.reason.trim(), by: who.user, at: now },
      updated_at: now,
    };
    save(next);
    remember(key, serialized, next);
    record(next, "complaint.cancelled", { reason: parsed.data.reason });
    return HttpResponse.json({ data: toWire(next) });
  }),

  /** CMPL-007 · QC chooses: a refund (managers by amount, then Accounts), a replacement, or none. */
  http.post(complaintPath("/remedy"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ id: params.complaintId, raw });
    const key = replay(request, serialized);
    if (key instanceof Response) return key;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    const parsed = remedyRequestSchema.safeParse(raw);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const who = caller();
    if (!QC_ROLES.has(who.role))
      return errorResponse(403, "forbidden", "Only QC chooses the remedy.");
    if (complaint.status !== "qc_approved") return moved();
    const body = parsed.data;
    if (body.kind === "refund") {
      const amount = Number(body.amount ?? "");
      if (!(amount > 0) || !/^\d+(\.\d{1,2})?$/.test(body.amount ?? "")) {
        return invalid({ amount: "above 0, two decimals at most" });
      }
      if (!body.payee_name?.trim()) return invalid({ payee_name: "who is paid" });
    } else if (
      body.amount != null ||
      body.payee_name != null ||
      body.paid_through_partner_id != null
    ) {
      return invalid({ amount: "a refund only" });
    }
    if (
      body.kind === "replacement" &&
      complaint.lines.every((line) => Number(line.defective_qty) === 0)
    ) {
      return errorResponse(422, "nothing_defective", "Nothing is marked defective.", {
        lines: "nothing defective",
      });
    }
    const now = new Date().toISOString();
    remedySerial += 1;
    const base = {
      id: mockUuid(MOCK_ID_SPACE.complaint, 0x7000 + remedySerial),
      kind: body.kind,
      remark: body.remark.trim(),
      chosen_by: who.user,
      chosen_at: now,
    };
    let remedy: MockRemedy;
    let status: MockComplaint["status"] = "remedy_pending";
    if (body.kind === "refund") {
      const roles = [
        ...refundManagersFor(body.amount ?? "0", mockDb.thresholds),
        "account_manager",
      ];
      const partner = MOCK_PARTNERS.find((item) => item.id === body.paid_through_partner_id);
      remedy = {
        ...base,
        status: "pending",
        refund: {
          amount: Number(body.amount).toFixed(2),
          payee_name: body.payee_name?.trim() ?? null,
          paid_through: partner === undefined ? null : { id: partner.id, name: partner.name },
          approval: {
            request_id: mockUuid(MOCK_ID_SPACE.approval, 0x70000 + remedySerial),
            status: "pending",
            steps: chainSteps(roles, 0x71000 + remedySerial * 10),
          },
          payment_reference: null,
        },
        replacement: null,
        completed_at: null,
      };
    } else if (body.kind === "replacement") {
      const order =
        mockDb.orders.find((item) => item.id === complaint.sales_order?.id) ?? mockDb.orders[0];
      remedy = {
        ...base,
        status: "pending",
        refund: null,
        // The mock names the order it would raise; the backend creates a free replacement order.
        replacement: {
          order:
            order === undefined
              ? null
              : { id: order.id, order_no: order.order_no, status: "submitted" },
        },
        completed_at: null,
      };
    } else {
      remedy = { ...base, status: "completed", refund: null, replacement: null, completed_at: now };
      status = "closed";
    }
    const next: MockComplaint = {
      ...complaint,
      remedy,
      status,
      closed_at: status === "closed" ? now : null,
      updated_at: now,
    };
    save(next);
    remember(key, serialized, next);
    if (body.kind === "refund") {
      record(next, "complaint.refund_requested", { amount: next.remedy?.refund?.amount });
    } else if (body.kind === "replacement") {
      record(next, "complaint.replacement_ordered", {
        order_no: next.remedy?.replacement?.order?.order_no ?? null,
      });
    } else {
      record(next, "complaint.remedy_chosen", { kind: "none", remark: body.remark });
      record(next, "complaint.closed", {});
    }
    const step = refundQueueStep(next);
    if (step !== null) mockDb.approvalSteps.push(step);
    return HttpResponse.json({ data: toWire(next) });
  }),

  /** CMPL-007 · Withdraw while open: a refund's approval is closed; back to QC to choose again. */
  http.post(complaintPath("/remedy/withdraw"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const raw: unknown = await request.json();
    const serialized = JSON.stringify({ id: params.complaintId, raw });
    const key = replay(request, serialized);
    if (key instanceof Response) return key;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    const parsed = withdrawRemedyRequestSchema.safeParse(raw);
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    if (!QC_ROLES.has(caller().role))
      return errorResponse(403, "forbidden", "Only QC withdraws the remedy.");
    if (complaint.status !== "remedy_pending" || complaint.remedy?.status !== "pending")
      return moved();
    closeRefundRows(complaint);
    const now = new Date().toISOString();
    const next: MockComplaint = {
      ...complaint,
      status: "qc_approved",
      remedy: { ...complaint.remedy, status: "withdrawn" },
      updated_at: now,
    };
    save(next);
    remember(key, serialized, next);
    record(next, "complaint.remedy_withdrawn", { remark: parsed.data.remark });
    return HttpResponse.json({ data: toWire(next) });
  }),

  /** CMPL-006 · One file, multipart: 10 MB, JPEG/PNG/WebP/HEIC/PDF, up to 10. */
  http.post(complaintPath("/attachments"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    if (!canFor(complaint, caller()).upload) {
      return errorResponse(403, "forbidden", "You may not add files to this complaint.");
    }
    const form = await request.formData();
    const file = form.get("file");
    const kind = form.get("kind");
    // A shape check, not `instanceof File`: the parsed part may come from another realm.
    if (file === null || typeof file === "string") return invalid({ file: "a file is needed" });
    if (typeof kind !== "string" || !ATTACHMENT_KINDS.some((item) => item === kind)) {
      return invalid({ kind: "photo, document or challan" });
    }
    if (file.size > COMPLAINT_ATTACHMENT_MAX_BYTES) {
      return errorResponse(422, "attachment_too_large", "Up to 10 MB.", { file: "over 10 MB" });
    }
    if (!COMPLAINT_ATTACHMENT_TYPES.some((type) => type === file.type)) {
      return errorResponse(422, "attachment_type", "JPEG, PNG, WebP, HEIC or PDF only.", {
        file: "not an accepted type",
      });
    }
    const same = complaint.attachments.find(
      (item) => item.filename === file.name && item.size_bytes === file.size,
    );
    if (same !== undefined) return HttpResponse.json({ data: same });
    if (complaint.attachments.length >= COMPLAINT_ATTACHMENTS_MAX) {
      return errorResponse(422, "too_many_attachments", "Up to 10 files.");
    }
    const attachment: MockComplaint["attachments"][number] = {
      id: mockUuid(MOCK_ID_SPACE.complaint, 0x9000 + mockDb.complaintFiles.size + 1),
      kind: ATTACHMENT_KINDS.find((item) => item === kind) ?? "photo",
      filename: file.name,
      content_type: file.type,
      size_bytes: file.size,
      preview: file.type !== "image/heic" && file.type !== "image/heif",
      uploaded_by: caller().user,
      uploaded_at: new Date().toISOString(),
    };
    mockDb.complaintFiles.set(attachment.id, file);
    const next: MockComplaint = {
      ...complaint,
      attachments: [...complaint.attachments, attachment],
    };
    save(next);
    record(next, "complaint.attachment_added", { filename: file.name });
    return HttpResponse.json({ data: attachment }, { status: 201 });
  }),

  http.get(complaintPath("/attachments/:attachmentId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    const attachment = complaint.attachments.find((item) => item.id === params.attachmentId);
    if (attachment === undefined) return errorResponse(404, "not_found", "No such file.");
    const file = mockDb.complaintFiles.get(attachment.id);
    // A seeded file has no bytes in the mock; a picture stands in for it.
    const url = file === undefined ? "/icon.svg" : objectUrlOf(file);
    return HttpResponse.json({
      data: { url, expires_at: new Date(Date.now() + 10 * 60_000).toISOString() },
    });
  }),

  http.delete(complaintPath("/attachments/:attachmentId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const complaint = findComplaint(params.complaintId);
    if (complaint instanceof Response) return complaint;
    if (!canFor(complaint, caller()).upload) {
      return errorResponse(409, "complaint_closed_for_upload", "The complaint is closed.");
    }
    const attachment = complaint.attachments.find((item) => item.id === params.attachmentId);
    if (attachment === undefined) return errorResponse(404, "not_found", "No such file.");
    // In a draft, whoever added it or an editor; after submit, only whoever added it.
    if (complaint.status !== "draft" && attachment.uploaded_by?.id !== caller().user.id) {
      return errorResponse(403, "forbidden", "Only whoever added this file can remove it.");
    }
    record(complaint, "complaint.attachment_removed", { filename: attachment.filename });
    save({
      ...complaint,
      attachments: complaint.attachments.filter((item) => item.id !== params.attachmentId),
    });
    return new HttpResponse(null, { status: 204 });
  }),

  /** CMPL-008 · The response and resolution targets, in working hours. */
  http.get(buildApiUrl("/complaint-sla-policies"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    return HttpResponse.json({ data: mockDb.slaPolicies });
  }),

  /** CMPL-008 · A new target from a day (masters edit): the one in force ends that day. */
  http.post(buildApiUrl("/complaint-sla-policies"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!can(mockPermissionsFor(readMockRole()), "masters", "edit")) {
      return errorResponse(403, "forbidden", "Only the administrator sets targets.");
    }
    const parsed = createSlaPolicyRequestSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    if (body.effective_from < todayInIndia()) {
      return errorResponse(422, "target_in_the_past", "A target cannot start in the past.", {
        effective_from: "today or later",
      });
    }
    if (body.resolution_hours < body.response_hours) {
      return invalid({ resolution_hours: "not less than the response target" });
    }
    const typeId = body.complaint_type_id ?? null;
    if (
      mockDb.slaPolicies.some(
        (row) =>
          row.severity === body.severity &&
          row.complaint_type_id === typeId &&
          row.effective_from === body.effective_from,
      )
    ) {
      return errorResponse(409, "target_exists", "A target already starts that day.");
    }
    const policy: SlaPolicyWire = {
      id: mockUuid(MOCK_ID_SPACE.complaint, 0xa000 + mockDb.slaPolicies.length + 1),
      severity: body.severity,
      complaint_type_id: typeId,
      response_hours: body.response_hours,
      resolution_hours: body.resolution_hours,
      business_hours_only: body.business_hours_only ?? true,
      effective_from: body.effective_from,
      // Up to the next one already scheduled, if any.
      effective_to:
        mockDb.slaPolicies
          .filter(
            (row) =>
              row.severity === body.severity &&
              row.complaint_type_id === typeId &&
              row.effective_from > body.effective_from,
          )
          .map((row) => row.effective_from)
          .sort()[0] ?? null,
    };
    mockDb.slaPolicies = [
      ...mockDb.slaPolicies.map((row) =>
        row.severity === body.severity &&
        row.complaint_type_id === typeId &&
        row.effective_from < body.effective_from &&
        (row.effective_to === null || row.effective_to > body.effective_from)
          ? { ...row, effective_to: body.effective_from }
          : row,
      ),
      policy,
    ];
    return HttpResponse.json({ data: mockDb.slaPolicies }, { status: 201 });
  }),
];
