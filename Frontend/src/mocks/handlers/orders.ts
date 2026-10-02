import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { TimelineEventWire, TimelinePageWire } from "@/features/leads/api/leads.schemas";
import {
  ORDER_STATUSES,
  ORDER_TYPES,
  ORDERABLE_TYPES,
  PAYMENT_TERMS,
  type DispatchWire,
  type OrderPageWire,
  type OrderStatus,
  type OrderWire,
} from "@/features/orders/api/orders.schemas";
import type { PdfLinkWire } from "@/features/quotations/api/quotations.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import type { Role } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { orderQueueStep, type MockApprovalStep } from "@/mocks/data/approvals";
import {
  applyDispatch,
  chainFor,
  chainSteps,
  milli,
  mockOrderFromQuotations,
  nextMockId,
  orderNumber,
  qtyText,
  statusFromLines,
  toOrderSummary,
} from "@/mocks/data/orders";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { newestFirst } from "@/mocks/data/timeline";
import { mockDb } from "@/mocks/db";

import { MOCK_CREATOR, newMockEvent } from "./lead-events";
import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * SO-001 … SO-004, DISP-002 · The backend's sales orders (backend/docs/api/orders.md,
 * dispatch.md): the list with its filters, the document, its PDF and history; a draft from
 * accepted quotations, its header, deleting it; submit into the approval chain, cancel;
 * recording and voiding dispatches, and closing short — with the backend's refusals.
 *
 * The chain is decided in the approvals inbox (handlers/approvals.ts), which calls
 * `decideOrderStep` here. Only the mock does this: an approved order's PDF is ready a few
 * seconds later.
 */

const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 100;
/** The backend stops counting here and says so with `total_capped`. */
const TOTAL_CEILING = 1000;
const PDF_LINK_MINUTES = 10;
const PDF_RENDER_MS = 2500;
const REMARK_MAX_LENGTH = 1000;

// ── helpers ─────────────────────────────────────────────────────────────────────

export function findOrder(orderId: string): OrderWire | undefined {
  return mockDb.orders.find((item) => item.id === orderId);
}

/** What time has done since the last read: an approved order's PDF finished rendering. */
function settle(order: OrderWire): OrderWire {
  const readyAt = mockDb.orderPdfReadyAt.get(order.id);
  if (readyAt !== undefined && Date.now() >= readyAt && order.pdf_state === "pending") {
    order.pdf_state = "ready";
    mockDb.orderPdfReadyAt.delete(order.id);
  }
  return order;
}

function validation(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function allowed(
  role: Role,
  module: "sales_orders" | "dispatch",
  action: "create" | "edit" | "delete",
): boolean {
  return can(mockPermissionsFor(role), module, action);
}

function isStatus(value: string): value is OrderStatus {
  return ORDER_STATUSES.some((status) => status === value);
}

/** Order number, party name or the mobile's digits (contains). */
function matchesSearch(order: OrderWire, q: string): boolean {
  const query = q.trim().toLowerCase();
  if (query === "") {
    return true;
  }
  const digits = query.replace(/\D/g, "");
  return (
    (order.order_no ?? "").toLowerCase().includes(query) ||
    order.party.name.toLowerCase().includes(query) ||
    (digits.length >= 3 && (order.party.mobile ?? "").replace(/\D/g, "").includes(digits))
  );
}

/** Replays a write sent again with its Idempotency-Key, or says it is fresh. */
function replayWrite(
  request: Request,
  body: unknown,
  status = 200,
): { kind: "fresh"; key: string; serialized: string } | { kind: "respond"; response: Response } {
  const key = request.headers.get("idempotency-key")?.trim() ?? "";
  if (key === "") {
    return {
      kind: "respond",
      response: errorResponse(
        400,
        "idempotency_key_required",
        "An Idempotency-Key header is required.",
      ),
    };
  }
  const serialized = JSON.stringify({
    path: new URL(request.url).pathname,
    method: request.method,
    body,
  });
  const replay = mockDb.orderWrites.get(key);
  if (replay === undefined) {
    return { kind: "fresh", key, serialized };
  }
  if (replay.body !== serialized) {
    return {
      kind: "respond",
      response: errorResponse(
        409,
        "idempotency_key_reused",
        "This Idempotency-Key was already used.",
      ),
    };
  }
  const order = findOrder(replay.orderId);
  return {
    kind: "respond",
    response:
      order === undefined
        ? new HttpResponse(null, { status: 204 })
        : HttpResponse.json({ data: order }, { status }),
  };
}

/** 404, or 409 status_changed when the screen showed another status. */
function orderAt(
  orderId: string,
  expectedStatus: unknown,
): { ok: true; order: OrderWire } | { ok: false; response: Response } {
  const order = findOrder(orderId);
  if (order === undefined) {
    return { ok: false, response: errorResponse(404, "not_found", "No such order.") };
  }
  if (typeof expectedStatus === "string" && expectedStatus !== order.status) {
    return {
      ok: false,
      response: errorResponse(
        409,
        "status_changed",
        "The order has moved on since you loaded it.",
        {
          status: order.status,
        },
      ),
    };
  }
  return { ok: true, order };
}

// ── history ─────────────────────────────────────────────────────────────────────

/** An order's history: derived once from what the seed says happened, then written to. */
function orderEventsOf(order: OrderWire): TimelineEventWire[] {
  const known = mockDb.orderEvents.get(order.id);
  if (known !== undefined) {
    return known;
  }
  const owner =
    order.owner === null ? null : { id: order.owner.id, full_name: order.owner.full_name };
  const at = (
    kind: string,
    occurredAt: string,
    payload: Record<string, unknown>,
    actor: TimelineEventWire["actor"] = owner,
  ): TimelineEventWire => ({
    ...newMockEvent(kind, { actor_name: actor?.full_name ?? "", ...payload }),
    occurred_at: occurredAt,
    actor,
  });
  const derived: TimelineEventWire[] = [at("order.created", order.created_at, {})];
  if (order.submitted_at !== null) {
    derived.push(at("order.submitted", order.submitted_at, { order_no: order.order_no }));
  }
  for (const step of order.approval?.steps ?? []) {
    const decidedAt = step.decided_at ?? null;
    const by = step.by ?? null;
    if (decidedAt !== null && step.decision !== null && step.decision !== undefined) {
      derived.push(
        at(
          "approval.decided",
          decidedAt,
          { seq: step.seq, role: step.role, decision: step.decision, remark: step.remark ?? null },
          by === null ? null : { id: by.id, full_name: by.full_name },
        ),
      );
    }
  }
  if (order.last_rejection !== null) {
    derived.push(
      at("order.returned", order.last_rejection.at, { remark: order.last_rejection.remark }, null),
    );
  }
  if (order.approved_at !== null) {
    derived.push(at("order.approved", order.approved_at, {}, null));
  }
  for (const dispatch of order.dispatches) {
    derived.push(
      at(
        "dispatch.recorded",
        dispatch.dispatched_at,
        { dispatch_no: dispatch.dispatch_no },
        dispatch.dispatched_by,
      ),
    );
  }
  if (order.closed_at !== null) {
    derived.push(at("order.closed_short", order.closed_at, { remark: order.close_remark }));
  }
  if (order.cancelled_at !== null) {
    derived.push(at("order.cancelled", order.cancelled_at, { remark: order.cancel_remark }));
  }
  derived.sort(newestFirst);
  mockDb.orderEvents.set(order.id, derived);
  return derived;
}

function recordOrderEvent(order: OrderWire, kind: string, payload: Record<string, unknown>): void {
  mockDb.orderEvents.set(order.id, [newMockEvent(kind, payload), ...orderEventsOf(order)]);
}

// ── the chain ───────────────────────────────────────────────────────────────────

/** Closes the order's waiting queue row, when its request ends before a decision. */
function closeQueueRow(order: OrderWire): void {
  const requestId = order.approval?.request_id;
  for (const step of mockDb.approvalSteps) {
    if (step.requestId === requestId && step.decision === null) {
      step.closed = "deleted";
    }
  }
}

function enqueue(step: MockApprovalStep | null): void {
  if (step !== null) {
    mockDb.approvalSteps.push(step);
  }
}

/**
 * APPR-001 · A decision on an order's step, from the approvals inbox: an approval passes it to
 * the next step or, at the last, approves the order (its PDF renders, the farmer is told); a
 * return sends it back to draft with the reason. The inbox has checked the step is open.
 */
export function decideOrderStep(
  order: OrderWire,
  stepId: string,
  decision: "approve" | "reject",
  remark: string | null,
  role: Role,
): void {
  const approval = order.approval;
  if (approval === null) {
    return;
  }
  const me = mockMeFor(role).data;
  const decidedAt = new Date().toISOString();
  const steps = approval.steps.map((item) =>
    item.id === stepId
      ? {
          ...item,
          decision,
          decided_role: me.role?.code === item.role ? null : (me.role?.code ?? null),
          by: { id: me.id, full_name: me.full_name },
          remark,
          decided_at: decidedAt,
        }
      : item,
  );
  const decided = steps.find((item) => item.id === stepId);
  order.approval = { ...approval, steps };
  recordOrderEvent(order, "approval.decided", {
    seq: decided?.seq ?? null,
    role: decided?.role ?? null,
    decision,
    remark,
  });

  if (decision === "reject") {
    order.status = "draft";
    order.approval = { ...order.approval, status: "rejected" };
    order.last_rejection = { remark: remark ?? "", role: decided?.role ?? "", at: decidedAt };
    recordOrderEvent(order, "order.returned", { remark });
    return;
  }
  const next = orderQueueStep(order);
  if (next !== null) {
    enqueue(next);
    return;
  }
  order.status = "approved";
  order.approval = { ...order.approval, status: "approved" };
  order.approved_at = decidedAt;
  order.pdf_state = "pending";
  order.confirmation = order.party.mobile ? "queued" : "no_mobile";
  mockDb.orderPdfReadyAt.set(order.id, Date.now() + PDF_RENDER_MS);
  recordOrderEvent(order, "order.approved", {});
}

// ── request bodies ──────────────────────────────────────────────────────────────

const remarkText = z.string().trim().max(REMARK_MAX_LENGTH);
const expectedStatus = z.enum(ORDER_STATUSES).nullish();

const createSchema = z.object({
  order_type: z.enum(ORDER_TYPES).default("commercial"),
  quotation_ids: z.array(z.string().min(1)).default([]),
  delivery_address: z.string().trim().max(500).nullish(),
  payment_terms: z.enum(PAYMENT_TERMS).default("full_payment"),
  remarks: z.string().trim().max(2000).nullish(),
  lines: z.array(z.unknown()).optional(),
});

const patchSchema = z.object({
  delivery_address: z.string().trim().max(500).nullish(),
  payment_terms: z.enum(PAYMENT_TERMS).nullish(),
  remarks: z.string().trim().max(2000).nullish(),
  expected_status: expectedStatus,
});

const remarkSchema = z.object({ remark: remarkText.min(1), expected_status: expectedStatus });

const dispatchSchema = z.object({
  dc_no: z.string().trim().max(60).nullish(),
  dc_date: z.iso.date().nullish(),
  invoice_no: z.string().trim().max(60).nullish(),
  invoice_date: z.iso.date().nullish(),
  dispatched_at: z.iso.datetime({ offset: true }),
  transporter: z.string().trim().max(120).nullish(),
  vehicle_no: z.string().trim().max(20).nullish(),
  lines: z.array(
    z.object({ order_line_id: z.string().min(1), qty: z.string().regex(/^\d+(\.\d+)?$/) }),
  ),
});

function orderableType(value: string): value is (typeof ORDERABLE_TYPES)[number] {
  return ORDERABLE_TYPES.some((type) => type === value);
}

function nextSerial(): number {
  return (
    mockDb.orders.reduce((max, item) => {
      const serial = Number(item.order_no?.split("/").at(-1) ?? "0");
      return Number.isFinite(serial) ? Math.max(max, serial) : max;
    }, 0) + 1
  );
}

/** A live order already carries the quotation: one live order each. */
function onLiveOrder(quotationId: string): boolean {
  return mockDb.orders.some(
    (order) =>
      order.status !== "cancelled" &&
      order.quotations.some((quotation) => quotation.id === quotationId),
  );
}

// ── handlers ────────────────────────────────────────────────────────────────────

export const orderHandlers = [
  http.get(buildApiUrl("/orders"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT),
    );
    const cursorParam = url.searchParams.get("cursor");
    const offset = cursorParam === null ? 0 : decodeCursor(cursorParam);
    if (offset === null) {
      return validation({ cursor: "malformed cursor" });
    }
    const statuses = (url.searchParams.get("status") ?? "")
      .split(",")
      .filter((value) => value !== "");
    if (!statuses.every(isStatus)) {
      return validation({ status: "unknown status" });
    }
    const orderType = url.searchParams.get("order_type");
    const owner = url.searchParams.get("owner");
    const leadId = url.searchParams.get("lead_id");
    const quotationId = url.searchParams.get("quotation_id");
    const q = url.searchParams.get("q") ?? "";
    const matches =
      scenario === "empty"
        ? []
        : mockDb.orders.filter(
            (order) =>
              (statuses.length === 0 || statuses.includes(order.status)) &&
              (orderType === null || order.order_type === orderType) &&
              (owner === null || order.owner?.id === (owner === "me" ? MOCK_CREATOR?.id : owner)) &&
              (leadId === null || order.lead?.id === leadId) &&
              (quotationId === null ||
                order.quotations.some((quotation) => quotation.id === quotationId)) &&
              matchesSearch(order, q),
          );
    const counted = url.searchParams.get("include_total") === "true";
    const hasMore = offset + limit < matches.length;
    const body: OrderPageWire = {
      data: matches.slice(offset, offset + limit).map((order) => toOrderSummary(settle(order))),
      meta: {
        limit,
        next_cursor: hasMore ? encodeCursor(offset + limit) : null,
        total: counted ? Math.min(matches.length, TOTAL_CEILING) : null,
        total_capped: counted && matches.length > TOTAL_CEILING,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/orders/:orderId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const order = findOrder(String(params.orderId));
    return order === undefined
      ? errorResponse(404, "not_found", "No such order.")
      : HttpResponse.json({ data: settle(order) });
  }),

  http.get(buildApiUrl("/orders/:orderId/pdf"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const found = findOrder(String(params.orderId));
    if (found === undefined || found.approved_at === null) {
      return errorResponse(404, "not_found", "An order has a PDF once it is approved.");
    }
    const order = settle(found);
    if (order.status === "cancelled") {
      return errorResponse(409, "order_cancelled", "The order was cancelled.");
    }
    if (order.pdf_state === "pending") {
      return errorResponse(409, "pdf_pending", "The PDF is still being prepared.");
    }
    if (order.pdf_state === "failed") {
      return errorResponse(409, "pdf_failed", order.pdf_error ?? "The PDF could not be made.");
    }
    const filename = `${(order.order_no ?? "order").replace(/\//g, "-")}.pdf`;
    const body: PdfLinkWire = {
      data: {
        // TODO(SO-002): the mock has no PDFs; the real link is a signed storage URL.
        url: `https://files.polysil.example/orders/${filename}`,
        expires_at: new Date(Date.now() + PDF_LINK_MINUTES * 60 * 1000).toISOString(),
        filename,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/orders/:orderId/timeline"), async ({ params, request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const order = findOrder(String(params.orderId));
    if (order === undefined) {
      return errorResponse(404, "not_found", "No such order.");
    }
    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT),
    );
    const cursorParam = url.searchParams.get("cursor");
    const offset = cursorParam === null ? 0 : decodeCursor(cursorParam);
    if (offset === null) {
      return validation({ cursor: "malformed cursor" });
    }
    const events = scenario === "empty" ? [] : [...orderEventsOf(order)].sort(newestFirst);
    const hasMore = offset + limit < events.length;
    const body: TimelinePageWire = {
      data: events.slice(offset, offset + limit),
      meta: { limit, next_cursor: hasMore ? encodeCursor(offset + limit) : null },
    };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/orders"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw, 201);
    if (replay.kind === "respond") return replay.response;
    if (!allowed(readMockRole(), "sales_orders", "create")) {
      return errorResponse(403, "forbidden", "You cannot place orders.");
    }
    const parsed = createSchema.safeParse(raw);
    if (!parsed.success) {
      return validation({ order_type: "check the order's fields" });
    }
    const body = parsed.data;
    if (!orderableType(body.order_type)) {
      return errorResponse(
        422,
        "order_type_unsupported",
        "Only commercial and industrial orders are built.",
        {
          order_type: body.order_type,
        },
      );
    }
    if (body.quotation_ids.length === 0) {
      // TODO(SO-005): a direct order, typed in line by line.
      return validation({ quotation_ids: "at least one accepted quotation" });
    }
    const quotations = body.quotation_ids.map((id) =>
      mockDb.quotations.find((item) => item.id === id),
    );
    for (const [index, quotation] of quotations.entries()) {
      if (quotation === undefined) {
        return errorResponse(404, "not_found", "No such quotation.");
      }
      if (quotation.status !== "accepted" || quotation.superseded_by !== null) {
        return errorResponse(
          422,
          "quotation_not_accepted",
          `Quotation ${quotation.quote_no ?? "draft"} is ${quotation.status}; only an accepted, current quotation is ordered.`,
          { quotation_ids: body.quotation_ids[index] ?? "" },
        );
      }
      if (onLiveOrder(quotation.id)) {
        return errorResponse(409, "quotation_on_order", "The quotation is already on an order.", {
          quotation_ids: quotation.id,
        });
      }
    }
    const found = quotations.filter((item) => item !== undefined);
    const first = found[0];
    if (first === undefined) {
      return validation({ quotation_ids: "at least one accepted quotation" });
    }
    const disagrees = found.find(
      (item) =>
        item.partner?.id !== first.partner?.id ||
        item.place_of_supply.territory.id !== first.place_of_supply.territory.id,
    );
    if (disagrees !== undefined) {
      const field = disagrees.partner?.id !== first.partner?.id ? "partner_id" : "place_of_supply";
      return errorResponse(422, "quotations_disagree", "The quotations disagree.", {
        [field]: "differs",
      });
    }
    if (new Set(found.map((item) => item.lead?.id)).size > 1 && first.partner === null) {
      return errorResponse(422, "partner_required", "Orders from several leads need their dealer.");
    }
    const order = mockOrderFromQuotations({
      id: mockUuid(MOCK_ID_SPACE.order, 1000 + mockDb.orderWrites.size),
      quotations: found,
      lead: mockDb.leads.find((lead) => lead.id === first.lead?.id),
      orderType: body.order_type,
      deliveryAddress: body.delivery_address ?? null,
      paymentTerms: body.payment_terms,
      remarks: body.remarks ?? null,
      createdAt: new Date().toISOString(),
    });
    const me = mockMeFor(readMockRole()).data;
    order.owner = { id: me.id, full_name: me.full_name };
    mockDb.orders.unshift(order);
    mockDb.orderWrites.set(replay.key, { body: replay.serialized, orderId: order.id });
    recordOrderEvent(order, "order.created", {});
    return HttpResponse.json({ data: order }, { status: 201 });
  }),

  http.patch(buildApiUrl("/orders/:orderId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;
    const parsed = patchSchema.safeParse(raw);
    if (!parsed.success) {
      return validation({ delivery_address: "check the header's fields" });
    }
    const target = orderAt(String(params.orderId), parsed.data.expected_status);
    if (!target.ok) return target.response;
    const { order } = target;
    if (order.status !== "draft") {
      return errorResponse(409, "order_not_draft", "Only a draft can be changed.");
    }
    const body = parsed.data;
    if (body.delivery_address !== undefined) order.delivery_address = body.delivery_address || null;
    if (body.payment_terms !== undefined && body.payment_terms !== null)
      order.payment_terms = body.payment_terms;
    if (body.remarks !== undefined) order.remarks = body.remarks || null;
    mockDb.orderWrites.set(replay.key, { body: replay.serialized, orderId: order.id });
    recordOrderEvent(order, "order.updated", {});
    return HttpResponse.json({ data: order });
  }),

  http.delete(buildApiUrl("/orders/:orderId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const replay = replayWrite(request, null, 204);
    if (replay.kind === "respond") return replay.response;
    if (!allowed(readMockRole(), "sales_orders", "delete")) {
      return errorResponse(403, "forbidden", "Only a holder of delete removes a draft.");
    }
    const order = findOrder(String(params.orderId));
    if (order === undefined) {
      return errorResponse(404, "not_found", "No such order.");
    }
    if (order.order_no !== null || order.status !== "draft") {
      return errorResponse(
        409,
        "order_was_submitted",
        "A submitted order is cancelled, not deleted.",
      );
    }
    mockDb.orders = mockDb.orders.filter((item) => item.id !== order.id);
    mockDb.orderWrites.set(replay.key, { body: replay.serialized, orderId: order.id });
    return new HttpResponse(null, { status: 204 });
  }),

  http.post(buildApiUrl("/orders/:orderId/submit"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;
    const parsed = z.object({ expected_status: expectedStatus }).safeParse(raw);
    const target = orderAt(
      String(params.orderId),
      parsed.success ? parsed.data.expected_status : null,
    );
    if (!target.ok) return target.response;
    const { order } = target;
    if (order.status !== "draft") {
      return errorResponse(409, "order_not_draft", "Only a draft can be submitted.");
    }
    if (order.lines.length === 0) {
      return errorResponse(422, "no_lines", "Add a line first.");
    }
    if (Number(order.totals.total) <= 0) {
      return errorResponse(422, "zero_total", "The order's total is zero.");
    }
    order.order_no ??= orderNumber(nextSerial());
    order.status = "submitted";
    order.submitted_at = new Date().toISOString();
    order.approval = {
      request_id: mockUuid(MOCK_ID_SPACE.approval, 80_000 + mockDb.approvalSteps.length),
      status: "pending",
      steps: chainSteps(
        chainFor(order.totals.total, mockDb.thresholds, order.territory.id),
        200_000 + mockDb.approvalSteps.length * 10,
      ),
    };
    enqueue(orderQueueStep(order));
    mockDb.orderWrites.set(replay.key, { body: replay.serialized, orderId: order.id });
    recordOrderEvent(order, "order.submitted", { order_no: order.order_no });
    return HttpResponse.json({ data: order });
  }),

  http.post(buildApiUrl("/orders/:orderId/cancel"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;
    const parsed = remarkSchema.safeParse(raw);
    if (!parsed.success) {
      return validation({ remark: "Say why." });
    }
    const target = orderAt(String(params.orderId), parsed.data.expected_status);
    if (!target.ok) return target.response;
    const { order } = target;
    if (order.lines.some((line) => milli(line.qty_dispatched) > 0)) {
      return errorResponse(
        409,
        "order_dispatched",
        "Something has shipped; close it short instead.",
      );
    }
    if (!["draft", "submitted", "approved"].includes(order.status)) {
      return errorResponse(409, "order_not_cancellable", "This order cannot be cancelled.");
    }
    const role = readMockRole();
    const holdsDelete = allowed(role, "sales_orders", "delete");
    if (order.status === "approved" && !holdsDelete) {
      return errorResponse(403, "forbidden", "Only a holder of delete cancels an approved order.");
    }
    if (!holdsDelete && order.owner?.id !== mockMeFor(role).data.id) {
      return errorResponse(403, "forbidden", "The owner cancels their own order.");
    }
    closeQueueRow(order);
    if (order.approval?.status === "pending") {
      order.approval = { ...order.approval, status: "cancelled" };
    }
    order.status = "cancelled";
    order.cancelled_at = new Date().toISOString();
    order.cancel_remark = parsed.data.remark;
    mockDb.orderWrites.set(replay.key, { body: replay.serialized, orderId: order.id });
    recordOrderEvent(order, "order.cancelled", { remark: parsed.data.remark });
    return HttpResponse.json({ data: order });
  }),

  http.post(buildApiUrl("/orders/:orderId/close-short"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;
    if (!allowed(readMockRole(), "dispatch", "edit")) {
      return errorResponse(403, "forbidden", "Dispatch closes an order short.");
    }
    const parsed = remarkSchema.safeParse(raw);
    if (!parsed.success) {
      return validation({ remark: "Say why." });
    }
    const target = orderAt(String(params.orderId), parsed.data.expected_status);
    if (!target.ok) return target.response;
    const { order } = target;
    if (order.status !== "approved" && order.status !== "partially_dispatched") {
      return errorResponse(
        409,
        "order_not_dispatchable",
        "Only an approved order is closed short.",
      );
    }
    order.lines = order.lines.map((line) => ({
      ...line,
      qty_short: line.qty_open,
      qty_open: "0.000",
    }));
    order.status = "closed_short";
    order.closed_at = new Date().toISOString();
    order.close_remark = parsed.data.remark;
    mockDb.orderWrites.set(replay.key, { body: replay.serialized, orderId: order.id });
    recordOrderEvent(order, "order.closed_short", { remark: parsed.data.remark });
    return HttpResponse.json({ data: order });
  }),

  http.post(buildApiUrl("/orders/:orderId/dispatches"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const key = request.headers.get("idempotency-key")?.trim() ?? "";
    if (key === "") {
      return errorResponse(
        400,
        "idempotency_key_required",
        "An Idempotency-Key header is required.",
      );
    }
    const serialized = JSON.stringify({ path: new URL(request.url).pathname, body: raw });
    const replay = mockDb.orderWrites.get(key);
    if (replay !== undefined) {
      if (replay.body !== serialized) {
        return errorResponse(
          409,
          "idempotency_key_reused",
          "This Idempotency-Key was already used.",
        );
      }
      const dispatch = findOrder(replay.orderId)?.dispatches.at(-1);
      return dispatch === undefined
        ? errorResponse(404, "not_found", "No such dispatch.")
        : HttpResponse.json({ data: dispatch }, { status: 201 });
    }
    if (!allowed(readMockRole(), "dispatch", "create")) {
      return errorResponse(403, "forbidden", "Dispatch records what left.");
    }
    const parsed = dispatchSchema.safeParse(raw);
    if (!parsed.success) {
      return validation({ dispatched_at: "When the goods left, with the time." });
    }
    const order = findOrder(String(params.orderId));
    if (order === undefined) {
      return errorResponse(404, "not_found", "No such order.");
    }
    if (order.status !== "approved" && order.status !== "partially_dispatched") {
      return errorResponse(409, "order_not_dispatchable", "Only an approved order ships.");
    }
    const body = parsed.data;
    if (Date.parse(body.dispatched_at) > Date.now() + 60_000) {
      return validation({ dispatched_at: "Cannot be in the future." });
    }
    if (body.lines.length === 0) {
      return validation({ lines: "At least one line." });
    }
    const fields: Record<string, string> = {};
    const seen = new Set<string>();
    let code = "validation_error";
    for (const [index, sent] of body.lines.entries()) {
      const line = order.lines.find((item) => item.id === sent.order_line_id);
      const at = `lines[${String(index)}].qty`;
      if (seen.has(sent.order_line_id)) {
        fields[`lines[${String(index)}].order_line_id`] = "This line is already in the dispatch.";
        code = "duplicate_line";
      } else if (line === undefined) {
        fields[`lines[${String(index)}].order_line_id`] = "Not a line of this order.";
        code = "line_not_on_order";
      } else if (milli(sent.qty) <= 0) {
        fields[at] = "More than zero.";
      } else if ((sent.qty.split(".")[1] ?? "").replace(/0+$/, "").length > line.uom_decimals) {
        fields[at] =
          line.uom_decimals === 0
            ? "Whole units only."
            : `At most ${String(line.uom_decimals)} decimals.`;
        code = "unit_precision";
      } else if (milli(sent.qty) > milli(line.qty_open)) {
        fields[at] = `At most ${line.qty_open}, what is still open.`;
        code = "over_open_quantity";
      }
      seen.add(sent.order_line_id);
    }
    if (Object.keys(fields).length > 0) {
      return errorResponse(422, code, "Some lines need correcting.", fields);
    }
    const warnings: string[] = [];
    if (body.invoice_date && body.dc_date && body.invoice_date < body.dc_date) {
      warnings.push("invoice_before_dc");
    }
    const invoiceNo = body.invoice_no ?? null;
    if (
      invoiceNo !== null &&
      invoiceNo !== "" &&
      mockDb.orders.some((item) =>
        item.dispatches.some(
          (dispatch) => dispatch.invoice_no === invoiceNo && dispatch.voided_at === null,
        ),
      )
    ) {
      warnings.push("duplicate_invoice_no");
    }
    const sequence = order.dispatches.length + 1;
    const me = mockMeFor(readMockRole()).data;
    const dispatch: DispatchWire = {
      id: nextMockId("dispatch"),
      order: { id: order.id, order_no: order.order_no, party_name: order.party.name },
      dispatch_no: `D/${order.order_no ?? "draft"}/${String(sequence)}`,
      dc_no: body.dc_no || null,
      dc_date: body.dc_date ?? null,
      invoice_no: invoiceNo || null,
      invoice_date: body.invoice_date ?? null,
      dispatched_at: body.dispatched_at,
      transporter: body.transporter || null,
      vehicle_no: body.vehicle_no || null,
      dispatched_by: { id: me.id, full_name: me.full_name },
      voided_at: null,
      void_remark: null,
      lines: body.lines.map((sent) => ({
        order_line_id: sent.order_line_id,
        line_no: order.lines.find((line) => line.id === sent.order_line_id)?.line_no ?? 0,
        qty: qtyText(milli(sent.qty)),
      })),
      warnings,
    };
    order.dispatches = [...order.dispatches, dispatch];
    applyDispatch(order, dispatch, 1);
    mockDb.orderWrites.set(key, { body: serialized, orderId: order.id });
    recordOrderEvent(order, "dispatch.recorded", { dispatch_no: dispatch.dispatch_no });
    return HttpResponse.json({ data: dispatch }, { status: 201 });
  }),

  http.post(buildApiUrl("/dispatches/:dispatchId/void"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;
    if (!allowed(readMockRole(), "dispatch", "edit")) {
      return errorResponse(403, "forbidden", "Dispatch voids a dispatch.");
    }
    const parsed = remarkSchema.safeParse(raw);
    if (!parsed.success) {
      return validation({ remark: "Say why." });
    }
    const order = mockDb.orders.find((item) =>
      item.dispatches.some((dispatch) => dispatch.id === params.dispatchId),
    );
    const dispatch = order?.dispatches.find((item) => item.id === params.dispatchId);
    if (order === undefined || dispatch === undefined) {
      return errorResponse(404, "not_found", "No such dispatch.");
    }
    if (
      typeof parsed.data.expected_status === "string" &&
      parsed.data.expected_status !== order.status
    ) {
      return errorResponse(409, "status_changed", "The order has moved on since you loaded it.", {
        status: order.status,
      });
    }
    if (dispatch.voided_at !== null) {
      return errorResponse(409, "dispatch_voided", "This dispatch is already void.");
    }
    if (order.status === "closed_short" || order.status === "cancelled") {
      return errorResponse(409, "order_closed", "The order is closed.");
    }
    const voided: DispatchWire = {
      ...dispatch,
      voided_at: new Date().toISOString(),
      void_remark: parsed.data.remark,
    };
    order.dispatches = order.dispatches.map((item) => (item.id === dispatch.id ? voided : item));
    applyDispatch(order, dispatch, -1);
    order.status = statusFromLines(order.lines);
    mockDb.orderWrites.set(replay.key, { body: replay.serialized, orderId: order.id });
    recordOrderEvent(order, "dispatch.voided", {
      dispatch_no: dispatch.dispatch_no,
      remark: parsed.data.remark,
    });
    return HttpResponse.json({ data: order });
  }),
];
