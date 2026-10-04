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
  type PatchComplaintRequest,
} from "@/features/complaints/api/complaints.schemas";
import type { TimelineEventWire, TimelinePageWire } from "@/features/leads/api/leads.schemas";
import { summarizeSchemaIssues } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { slaFor, type MockComplaint } from "@/mocks/data/complaints";
import { mockLookupRows } from "@/mocks/data/lookups";
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
    upload: false,
    remedy: false,
    withdraw: false,
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
      complaint.check.decision === "approve" ? "complaint.checked" : "complaint.returned",
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
    record(next, approve ? "complaint.checked" : "complaint.returned", { remark: body.remark });
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
];
