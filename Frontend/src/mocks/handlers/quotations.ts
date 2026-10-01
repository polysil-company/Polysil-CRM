import { http, HttpResponse } from "msw";
import { z } from "zod";

import type {
  LeadWire,
  TimelinePageWire,
  TimelineEventWire,
} from "@/features/leads/api/leads.schemas";
import {
  PRICED_SALES_TYPES,
  QUOTATION_ANSWERS,
  QUOTATION_STATUSES,
  SALES_TYPES,
  type PublicQuotationWire,
  type QuotationVersionsWire,
  type SendGate,
  type PdfLinkWire,
  type ProductPageWire,
  type QuotationLineWire,
  type QuotePreviewWire,
  type QuotationPageWire,
  type QuotationStatus,
  type QuotationWire,
} from "@/features/quotations/api/quotations.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { quotationApproverFor } from "@/mocks/data/approvals";
import {
  MOCK_PRODUCTS,
  mockDraft,
  mockLine,
  mockShareUrl,
  priceListItemId,
  toQuotationSummary,
  totalsOf,
  withLines,
} from "@/mocks/data/quotations";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { newestFirst } from "@/mocks/data/timeline";
import { mockDb } from "@/mocks/db";

import { MOCK_CREATOR, newMockEvent, recordLeadEvent } from "./lead-events";
import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * QUOT-001 … QUOT-003 · The backend's quotation reads (backend/docs/api/quotations.md): the
 * list with its filters, cursor paging and capped total; the document; and the PDF link,
 * with 404 on a draft and 409 while the PDF renders or after it failed.
 * QUOT-004, QUOT-005, MSTR-003 · The builder: product search, the pricing preview, and saving a
 * draft — create, header and lines — with the backend's refusals: lead_not_qualified,
 * sales_type_unsupported, status_changed, quotation_not_draft and rate_changed.
 * QUOT-006 … QUOT-011 · The lifecycle: send (with the discount gate), discount approval,
 * the customer's answer, revise and versions, the history, and deleting a draft — with the
 * lead moving beside the document as on the backend.
 *
 * QUOT-012 · The customer's page: the shared view, and the PDF open that records the view.
 *
 * Only the mock does this, so the flow can be tried end to end: a just-sent PDF is ready a
 * few seconds later. A discount request waits in the approvals inbox (handlers/approvals.ts).
 */

const DEFAULT_LIMIT = 25;
const MAX_LIMIT = 100;
/** The backend stops counting here and says so with `total_capped`. */
const TOTAL_CEILING = 1000;
const PDF_LINK_MINUTES = 10;

function isStatus(value: string): value is QuotationStatus {
  return QUOTATION_STATUSES.some((status) => status === value);
}

/** Number (contains), party name (contains) or the mobile's digits (contains). */
function matchesSearch(quotation: QuotationWire, q: string): boolean {
  const query = q.trim().toLowerCase();
  if (query === "") {
    return true;
  }
  const digits = query.replace(/\D/g, "");
  return (
    (quotation.quote_no ?? "").toLowerCase().includes(query) ||
    quotation.party.name.toLowerCase().includes(query) ||
    (digits.length >= 3 && quotation.party.mobile.includes(digits))
  );
}

/** A lead's quotations include those on leads merged into it, as on the backend. */
function onLead(quotation: QuotationWire, leadId: string): boolean {
  if (quotation.lead?.id === leadId) {
    return true;
  }
  const lead = mockDb.leads.find((item) => item.id === quotation.lead?.id);
  return lead?.merged_into?.id === leadId;
}

/** A lead may carry a quotation from qualified on (backend: `lead_not_qualified` before). */
const QUOTABLE_STAGES = ["qualified", "quoted", "negotiation", "won"];
/** The mock's one stand-in rate, so the indicative-pricing banner can be previewed. */
const PROVISIONAL_PRODUCT_INDEX = 1;

const lineInSchema = z.object({
  product_id: z.string().min(1),
  qty: z.coerce.number(),
  discount_pct: z.coerce.number().default(0),
  discount2_pct: z.coerce.number().default(0),
  discount3_pct: z.coerce.number().default(0),
  price_list_item_id: z.string().nullish(),
  gst_rate_id: z.string().nullish(),
});

type LineIn = z.infer<typeof lineInSchema>;

const partySchema = z.object({
  name: z.string().trim().min(1).max(200),
  mobile: z.string().trim().min(10),
  address: z.string().nullish(),
  gstin: z.string().nullish(),
});

/**
 * Prices lines as the backend's preview does, or names the first field it refuses:
 * an unknown product, a quantity of zero or with more decimals than the unit takes, a
 * discount outside 0–100.
 */
function priceLines(
  lines: readonly LineIn[],
): { ok: true; lines: QuotationLineWire[] } | { ok: false; fields: Record<string, string> } {
  const fields: Record<string, string> = {};
  const priced: QuotationLineWire[] = [];
  for (const [index, line] of lines.entries()) {
    const product = MOCK_PRODUCTS.find((item) => item.id === line.product_id);
    if (product === undefined) {
      fields[`lines[${String(index)}].product_id`] = "product_inactive: not an active product";
      continue;
    }
    const decimals = (String(line.qty).split(".")[1] ?? "").length;
    if (!(line.qty > 0)) {
      fields[`lines[${String(index)}].qty`] = "must be greater than 0";
    } else if (decimals > product.uomDecimals) {
      fields[`lines[${String(index)}].qty`] =
        product.uomDecimals === 0
          ? `${product.uom} takes whole numbers`
          : `${product.uom} takes at most ${String(product.uomDecimals)} decimals`;
    }
    const discounts = [line.discount_pct, line.discount2_pct, line.discount3_pct] as const;
    for (const [tier, pct] of discounts.entries()) {
      if (pct < 0 || pct > 100) {
        fields[
          `lines[${String(index)}].${tier === 0 ? "discount_pct" : `discount${String(tier + 1)}_pct`}`
        ] = "between 0 and 100";
      }
    }
    priced.push(
      mockLine(
        index + 1,
        product,
        line.qty,
        discounts,
        MOCK_PRODUCTS.indexOf(product) === PROVISIONAL_PRODUCT_INDEX,
        mockDb.priceVersion,
      ),
    );
  }
  return Object.keys(fields).length > 0 ? { ok: false, fields } : { ok: true, lines: priced };
}

/** 409 rate_changed when a line was priced against a list row that is no longer in force. */
function rateChanges(lines: readonly LineIn[]): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const [index, line] of lines.entries()) {
    const product = MOCK_PRODUCTS.find((item) => item.id === line.product_id);
    if (
      product !== undefined &&
      line.price_list_item_id !== undefined &&
      line.price_list_item_id !== null &&
      line.price_list_item_id !== priceListItemId(product, mockDb.priceVersion)
    ) {
      const now = mockLine(index + 1, product, 1, [0, 0, 0], false, mockDb.priceVersion);
      fields[`lines[${String(index)}].rate`] = `now ${now.rate}`;
    }
  }
  return fields;
}

function validation(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

/** Idempotency-Key for quotation saves: 400 without one, a replay, or 409 for another body. */
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
  const replay = mockDb.quotationWrites.get(key);
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
  const quotation = mockDb.quotations.find((item) => item.id === replay.quotationId);
  return {
    kind: "respond",
    response:
      quotation === undefined
        ? errorResponse(404, "not_found", "No such quotation.")
        : HttpResponse.json({ data: quotation }, { status }),
  };
}

/** A draft that can still change, or the refusal: 404, 409 status_changed, 409 quotation_not_draft. */
function editableDraft(
  quotationId: string,
  expectedStatus: unknown,
): { ok: true; quotation: QuotationWire } | { ok: false; response: Response } {
  const quotation = mockDb.quotations.find((item) => item.id === quotationId);
  if (quotation === undefined) {
    return { ok: false, response: errorResponse(404, "not_found", "No such quotation.") };
  }
  if (typeof expectedStatus === "string" && expectedStatus !== quotation.status) {
    return {
      ok: false,
      response: errorResponse(
        409,
        "status_changed",
        "The quotation has moved on since you loaded it.",
        {
          status: quotation.status,
        },
      ),
    };
  }
  if (quotation.status !== "draft") {
    return {
      ok: false,
      response: errorResponse(409, "quotation_not_draft", "Only a draft can be changed."),
    };
  }
  return { ok: true, quotation };
}

// ── the lifecycle (QUOT-006 … QUOT-011) ──────────────────────────────────────

const VALIDITY_DAYS = 45;
const DAY_MS = 24 * 60 * 60 * 1000;
/** How long the mock's PDF "renders" after a send. */
const PDF_RENDER_MS = 2500;
const REMARK_MAX_LENGTH = 1000;
/** Answers are recorded on a quotation the customer has; negotiation → negotiation is not a move. */
const ANSWERABLE_STATUSES: readonly QuotationStatus[] = ["sent", "viewed", "negotiation"];
const REVISABLE_STATUSES: readonly QuotationStatus[] = [
  "sent",
  "viewed",
  "negotiation",
  "rejected",
  "expired",
];

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export function findQuotation(quotationId: string): QuotationWire | undefined {
  return mockDb.quotations.find((item) => item.id === quotationId);
}

function leadOf(quotation: QuotationWire): LeadWire | undefined {
  return mockDb.leads.find((item) => item.id === quotation.lead?.id);
}

/** What Send will do, from the discount and the latest approval request. */
function sendGateFor(quotation: QuotationWire): SendGate {
  if (quotation.discount?.approval_required !== true) {
    return "none_needed";
  }
  switch (quotation.approval?.status) {
    case "pending":
      return "pending";
    case "approved":
      return "approved";
    case "rejected":
      return "returned";
    case "cancelled":
      return "void";
    default:
      return "required";
  }
}

export function refreshGate(quotation: QuotationWire): void {
  if (quotation.discount !== null && quotation.discount !== undefined) {
    quotation.discount = { ...quotation.discount, send_gate: sendGateFor(quotation) };
  }
}

/** A quotation's history: derived once from what the seed says happened, then written to. */
function quotationEventsOf(quotation: QuotationWire): TimelineEventWire[] {
  const known = mockDb.quotationEvents.get(quotation.id);
  if (known !== undefined) {
    return known;
  }
  const actor = quotation.created_by;
  const at = (
    kind: string,
    occurredAt: string,
    payload: Record<string, unknown>,
  ): TimelineEventWire => ({
    ...newMockEvent(kind, { actor_name: actor?.full_name ?? "", ...payload }),
    occurred_at: occurredAt,
    actor,
  });
  const derived: TimelineEventWire[] = [at("quotation.created", quotation.created_at, {})];
  if (quotation.sent_at !== null) {
    derived.push(at("quotation.sent", quotation.sent_at, { from: "draft", to: "sent" }));
  }
  if (quotation.viewed_at !== null) {
    derived.push(at("quotation.viewed", quotation.viewed_at, { open_count: quotation.open_count }));
  }
  if (quotation.status === "negotiation" && quotation.viewed_at !== null) {
    derived.push(
      at(
        "quotation.negotiation",
        new Date(Date.parse(quotation.viewed_at) + DAY_MS).toISOString(),
        {
          from: "viewed",
          to: "negotiation",
        },
      ),
    );
  }
  const decidedAt = quotation.accepted_at ?? quotation.rejected_at;
  if (decidedAt !== null) {
    derived.push(
      at(`quotation.${quotation.status}`, decidedAt, {
        from: "viewed",
        to: quotation.status,
        remark: quotation.decision_remark,
      }),
    );
  }
  if (quotation.status === "expired" && quotation.valid_until !== null) {
    derived.push(
      at("quotation.expired", `${quotation.valid_until}T18:30:00.000Z`, {
        from: "sent",
        to: "expired",
      }),
    );
  }
  derived.sort(newestFirst);
  mockDb.quotationEvents.set(quotation.id, derived);
  return derived;
}

/** Writes an event on the quotation and, as the backend does, on its lead. */
export function recordQuotationEvent(
  quotation: QuotationWire,
  kind: string,
  payload: Record<string, unknown>,
): void {
  const event = newMockEvent(kind, payload);
  mockDb.quotationEvents.set(quotation.id, [event, ...quotationEventsOf(quotation)]);
  const lead = leadOf(quotation);
  if (lead !== undefined) {
    recordLeadEvent(lead, kind, {
      quotation_id: quotation.id,
      quote_no: quotation.quote_no,
      version: quotation.version,
      ...payload,
    });
  }
}

/** Moves the lead as the backend does beside the document, and says so on its history. */
function moveLead(quotation: QuotationWire, to: LeadWire["stage"]): void {
  const lead = leadOf(quotation);
  if (lead === undefined || lead.stage === to) {
    return;
  }
  const from = lead.stage;
  lead.stage = to;
  recordLeadEvent(lead, "lead.stage_changed", { from, to, quotation_id: quotation.id });
  for (const item of mockDb.quotations) {
    if (item.lead?.id === lead.id) {
      item.lead = { ...item.lead, stage: to };
    }
  }
}

/** 422 lead_not_open for a lost or merged lead, naming the stage. */
function leadNotOpen(quotation: QuotationWire): Response | null {
  const lead = leadOf(quotation);
  if (lead === undefined || (lead.stage !== "lost" && lead.stage !== "merged")) {
    return null;
  }
  return errorResponse(
    422,
    "lead_not_open",
    lead.stage === "lost" ? "The lead is lost; reopen it first." : "The lead was merged.",
    { stage: lead.stage },
  );
}

/** What time has done since the last read: a sent PDF finished rendering. */
export function settle(quotation: QuotationWire): QuotationWire {
  const readyAt = mockDb.pdfReadyAt.get(quotation.id);
  if (readyAt !== undefined && Date.now() >= readyAt && quotation.pdf_state === "pending") {
    quotation.pdf_state = "ready";
    mockDb.pdfReadyAt.delete(quotation.id);
  }
  return quotation;
}

/**
 * An edit or a delete cancels a pending or granted approval: it was for other figures. A
 * waiting request leaves the approver's inbox.
 */
function voidApproval(quotation: QuotationWire, reason: "edited" | "deleted"): void {
  const approval = quotation.approval;
  if (approval !== null && approval !== undefined && approval.status !== "rejected") {
    if (approval.status === "pending" || approval.status === "approved") {
      quotation.approval = { ...approval, status: "cancelled" };
      for (const step of mockDb.approvalSteps) {
        if (step.requestId === approval.request_id && step.decision === null) {
          step.closed = reason;
        }
      }
      recordQuotationEvent(quotation, "quotation.approval_cancelled", {});
    }
  }
  refreshGate(quotation);
}

function nextQuoteNo(): string {
  const highest = mockDb.quotations.reduce((max, item) => {
    const serial = Number(item.quote_no?.split("/").at(-1) ?? "0");
    return Number.isFinite(serial) ? Math.max(max, serial) : max;
  }, 0);
  return `QT/GJ/2026-27/${String(highest + 1).padStart(5, "0")}`;
}

/** Every version of the quotation's number, oldest first: the chain through `supersedes`. */
function versionsOf(quotation: QuotationWire): QuotationWire[] {
  let root = quotation;
  for (;;) {
    const previous = root.supersedes === null ? undefined : findQuotation(root.supersedes.id);
    if (previous === undefined) break;
    root = previous;
  }
  const chain: QuotationWire[] = [root];
  for (;;) {
    const current = chain.at(-1);
    const next = mockDb.quotations.find((item) => item.supersedes?.id === current?.id);
    if (next === undefined) break;
    chain.push(next);
  }
  return chain;
}

const remarkSchema = z.string().trim().max(REMARK_MAX_LENGTH).nullish();

/** The sent quotation a customer link points at. Drafts have no link. */
function sharedQuotation(token: string): QuotationWire | undefined {
  return mockDb.quotations.find((item) => item.share_url?.endsWith(`/q/${token}`) === true);
}

export const quotationHandlers = [
  http.get(buildApiUrl("/quotations"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    mockDb.quotations.forEach(settle);
    const url = new URL(request.url);
    const limit = Math.min(
      MAX_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_LIMIT) || DEFAULT_LIMIT),
    );
    const cursorParam = url.searchParams.get("cursor");
    const offset = cursorParam === null ? 0 : decodeCursor(cursorParam);
    if (offset === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        cursor: "malformed cursor",
      });
    }
    if (scenario === "contract") {
      // Deliberately wrong shape: exercises CONTRACT_VIOLATION handling end to end.
      return HttpResponse.json({ data: [{ id: 7, status: "lost" }], meta: { limit: "25" } });
    }

    const statuses = (url.searchParams.get("status") ?? "")
      .split(",")
      .map((status) => status.trim())
      .filter(isStatus);
    const salesType = url.searchParams.get("sales_type");
    const leadId = url.searchParams.get("lead_id");
    const q = url.searchParams.get("q") ?? "";
    const currentOnly = url.searchParams.get("current_only") !== "false";

    const matches =
      scenario === "empty"
        ? []
        : mockDb.quotations.filter(
            (quotation) =>
              (statuses.length === 0 || statuses.includes(quotation.status)) &&
              (salesType === null || salesType === "" || quotation.sales_type === salesType) &&
              (leadId === null || leadId === "" || onLead(quotation, leadId)) &&
              (!currentOnly || quotation.superseded_by === null) &&
              matchesSearch(quotation, q),
          );
    const counted = url.searchParams.get("include_total") === "true";
    const hasMore = offset + limit < matches.length;

    const body: QuotationPageWire = {
      data: matches.slice(offset, offset + limit).map(toQuotationSummary),
      meta: {
        limit,
        next_cursor: hasMore ? encodeCursor(offset + limit) : null,
        total: counted ? Math.min(matches.length, TOTAL_CEILING) : null,
        total_capped: counted && matches.length > TOTAL_CEILING,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/products"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const limit = Math.min(200, Number(url.searchParams.get("limit") ?? 50) || 50);
    const matches =
      scenario === "empty"
        ? []
        : MOCK_PRODUCTS.filter((product) => product.name.toLowerCase().includes(q));
    const body: ProductPageWire = {
      data: matches.slice(0, limit).map((product) => ({
        id: product.id,
        item_code: product.code,
        description: product.name,
        uom: product.uom,
        uom_decimals: product.uomDecimals,
        hsn_code: product.hsn,
        gst_slab: product.slab.toFixed(2),
        pack_multiple: null,
        is_active: true,
      })),
      meta: { page: 1, limit, total: matches.length },
    };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/pricing/quote-lines"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const parsed = z
      .object({
        place_of_supply_territory_id: z.string().min(1),
        lines: z.array(lineInSchema).min(1),
      })
      .safeParse(await request.json());
    if (!parsed.success) {
      return validation({ lines: "at least one line with a product and a quantity" });
    }
    const priced = priceLines(parsed.data.lines);
    if (!priced.ok) {
      return validation(priced.fields);
    }
    const provisional = priced.lines.filter((line) => line.provisional_fields.length > 0).length;
    const body: QuotePreviewWire = {
      data: {
        as_of: new Date().toISOString().slice(0, 10),
        intra_state: true,
        price_list_ids: [priced.lines[0]?.price_list_id ?? ""],
        lines: priced.lines.map(({ line_no: _lineNo, ...line }) => line),
        totals: totalsOf(priced.lines),
        warnings:
          provisional > 0
            ? [
                `provisional_pricing: ${String(provisional)} of ${String(priced.lines.length)} lines use stand-in rates or tax slabs`,
              ]
            : [],
      },
    };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/quotations"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw, 201);
    if (replay.kind === "respond") return replay.response;

    const parsed = z
      .object({
        lead_id: z.string().min(1),
        sales_type: z.enum(SALES_TYPES).optional(),
        party: partySchema.optional(),
        terms: z.string().max(2000).nullish(),
        lines: z.array(lineInSchema).max(200).default([]),
      })
      .safeParse(raw);
    if (!parsed.success) {
      return validation({ lead_id: "required" });
    }
    const body = parsed.data;
    const lead = mockDb.leads.find((item) => item.id === body.lead_id);
    if (lead === undefined) {
      return validation({ lead_id: "no such lead" });
    }
    if (!QUOTABLE_STAGES.includes(lead.stage)) {
      return errorResponse(422, "lead_not_qualified", "Qualify the lead before quoting it.", {
        lead_id: `the lead is ${lead.stage}`,
      });
    }
    const salesType = body.sales_type ?? "commercial";
    if (!PRICED_SALES_TYPES.some((type) => type === salesType)) {
      return errorResponse(
        422,
        "sales_type_unsupported",
        `${salesType} quotations wait on the client's rules; choose commercial or industrial.`,
        { sales_type: "not priced yet" },
      );
    }
    const changed = rateChanges(body.lines);
    if (Object.keys(changed).length > 0) {
      return errorResponse(
        409,
        "rate_changed",
        "Prices or tax changed since the preview. Review the new figures and save again.",
        changed,
      );
    }
    const priced = priceLines(body.lines);
    if (!priced.ok) {
      return validation(priced.fields);
    }

    const quotation = mockDraft({
      id: mockUuid(MOCK_ID_SPACE.quotation, 50_000 + mockDb.quotations.length),
      lead,
      salesType,
      party: body.party
        ? {
            name: body.party.name,
            mobile: body.party.mobile,
            address: body.party.address ?? null,
            gstin: body.party.gstin ?? null,
          }
        : { name: lead.farmer_name, mobile: lead.mobile, address: lead.village, gstin: null },
      terms: body.terms ?? null,
      lines: priced.lines,
      createdAt: new Date().toISOString(),
    });
    mockDb.quotations.unshift(quotation);
    // A new quotation has no seeded history to derive; this event starts it.
    mockDb.quotationEvents.set(quotation.id, []);
    recordQuotationEvent(quotation, "quotation.created", {});
    mockDb.quotationWrites.set(replay.key, { body: replay.serialized, quotationId: quotation.id });
    return HttpResponse.json({ data: quotation }, { status: 201 });
  }),

  http.patch(buildApiUrl("/quotations/:quotationId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;

    const parsed = z
      .object({
        sales_type: z.enum(SALES_TYPES).optional(),
        party: partySchema.optional(),
        terms: z.string().max(2000).nullish(),
        expected_status: z.string().optional(),
      })
      .safeParse(raw);
    if (!parsed.success) {
      return validation({ party: "check the party's name and mobile" });
    }
    const draft = editableDraft(String(params.quotationId), parsed.data.expected_status);
    if (!draft.ok) return draft.response;

    const { quotation } = draft;
    const body = parsed.data;
    if (body.sales_type !== undefined) {
      if (!PRICED_SALES_TYPES.some((type) => type === body.sales_type)) {
        return errorResponse(422, "sales_type_unsupported", "Not priced yet.", {
          sales_type: "not priced yet",
        });
      }
      quotation.sales_type = body.sales_type;
    }
    if (body.party !== undefined) {
      quotation.party = {
        name: body.party.name,
        mobile: body.party.mobile,
        address: body.party.address ?? null,
        gstin: body.party.gstin ?? null,
      };
    }
    if (body.terms !== undefined) {
      quotation.terms = body.terms ?? null;
    }
    quotation.updated_at = new Date().toISOString();
    voidApproval(quotation, "edited");
    recordQuotationEvent(quotation, "quotation.updated", {});
    mockDb.quotationWrites.set(replay.key, { body: replay.serialized, quotationId: quotation.id });
    return HttpResponse.json({ data: quotation });
  }),

  http.put(buildApiUrl("/quotations/:quotationId/lines"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;

    const parsed = z
      .object({ lines: z.array(lineInSchema).max(200), expected_status: z.string().optional() })
      .safeParse(raw);
    if (!parsed.success) {
      return validation({ lines: "check every line" });
    }
    const draft = editableDraft(String(params.quotationId), parsed.data.expected_status);
    if (!draft.ok) return draft.response;

    const changed = rateChanges(parsed.data.lines);
    if (Object.keys(changed).length > 0) {
      return errorResponse(
        409,
        "rate_changed",
        "Prices or tax changed since the preview. Review the new figures and save again.",
        changed,
      );
    }
    const priced = priceLines(parsed.data.lines);
    if (!priced.ok) {
      return validation(priced.fields);
    }
    const updated = withLines(draft.quotation, priced.lines);
    mockDb.quotations = mockDb.quotations.map((item) => (item.id === updated.id ? updated : item));
    voidApproval(updated, "edited");
    recordQuotationEvent(updated, "quotation.lines_replaced", { line_count: updated.lines.length });
    mockDb.quotationWrites.set(replay.key, { body: replay.serialized, quotationId: updated.id });
    return HttpResponse.json({ data: updated });
  }),

  http.post(buildApiUrl("/quotations/:quotationId/send"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;

    const parsed = z
      .object({
        channel: z.enum(["whatsapp", "none"]).default("whatsapp"),
        expected_status: z.string().optional(),
      })
      .safeParse(raw);
    if (!parsed.success) {
      return validation({ channel: "whatsapp or none" });
    }
    const draft = editableDraft(String(params.quotationId), parsed.data.expected_status);
    if (!draft.ok) return draft.response;
    const quotation = settle(draft.quotation);

    if (quotation.lines.length === 0) {
      return errorResponse(422, "no_lines", "Add at least one item before sending.");
    }
    const closed = leadNotOpen(quotation);
    if (closed !== null) return closed;
    const gate = sendGateFor(quotation);
    if (gate === "pending") {
      return errorResponse(409, "approval_pending", "The discount is waiting for approval.");
    }
    if (gate === "required" || gate === "void" || gate === "returned") {
      return errorResponse(
        409,
        "discount_approval_required",
        "The discount is above your limit; ask for approval first.",
        { send_gate: gate },
      );
    }
    const changed = rateChanges(
      quotation.lines.map((line) => ({
        product_id: line.product_id,
        qty: Number(line.qty),
        discount_pct: Number(line.discount_pct),
        discount2_pct: Number(line.discount2_pct),
        discount3_pct: Number(line.discount3_pct),
        price_list_item_id: line.price_list_item_id,
      })),
    );
    if (Object.keys(changed).length > 0) {
      return errorResponse(
        409,
        "rate_changed",
        "Prices or tax changed since the draft was saved. Save it again, then send.",
        changed,
      );
    }
    const predecessor =
      quotation.supersedes === null ? undefined : findQuotation(quotation.supersedes.id);
    if (predecessor?.status === "accepted") {
      return errorResponse(
        409,
        "predecessor_accepted",
        `Version ${String(predecessor.version)} was accepted meanwhile.`,
      );
    }

    const now = Date.now();
    const token = `mock-sent-${quotation.id.slice(-8)}`;
    quotation.quote_no = predecessor?.quote_no ?? nextQuoteNo();
    quotation.status = "sent";
    quotation.sent_at = new Date(now).toISOString();
    quotation.valid_until = new Date(now + VALIDITY_DAYS * DAY_MS).toISOString().slice(0, 10);
    quotation.share_url = mockShareUrl(token);
    quotation.pdf_state = "pending";
    quotation.pdf_error = null;
    quotation.discount = null;
    quotation.updated_at = quotation.sent_at;
    mockDb.pdfReadyAt.set(quotation.id, now + PDF_RENDER_MS);
    if (predecessor !== undefined) {
      predecessor.superseded_by = { id: quotation.id, version: quotation.version };
    }
    recordQuotationEvent(quotation, "quotation.sent", {
      from: "draft",
      to: "sent",
      channel: parsed.data.channel,
    });
    if (leadOf(quotation)?.stage === "qualified") {
      moveLead(quotation, "quoted");
    }
    mockDb.quotationWrites.set(replay.key, { body: replay.serialized, quotationId: quotation.id });
    return HttpResponse.json({ data: quotation });
  }),

  http.post(
    buildApiUrl("/quotations/:quotationId/request-approval"),
    async ({ params, request }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;

      const raw: unknown = await request.json();
      const replay = replayWrite(request, raw);
      if (replay.kind === "respond") return replay.response;

      const parsed = z.object({ remark: remarkSchema }).safeParse(raw);
      if (!parsed.success) {
        return validation({ remark: `at most ${String(REMARK_MAX_LENGTH)} characters` });
      }
      const draft = editableDraft(String(params.quotationId), undefined);
      if (!draft.ok) return draft.response;
      const quotation = settle(draft.quotation);

      const gate = sendGateFor(quotation);
      if (gate === "none_needed" || gate === "approved") {
        return errorResponse(
          409,
          "approval_not_required",
          "The discount is within your limit; send it.",
        );
      }
      if (gate === "pending") {
        return errorResponse(409, "approval_pending", "A request is already waiting.");
      }
      const effective = Number(quotation.discount?.effective_pct ?? "0");
      const approverRole = quotationApproverFor(effective, mockDb.thresholds);
      if (approverRole === null) {
        return errorResponse(
          422,
          "no_approver",
          "No manager's limit covers this discount. Lower it, or ask an administrator.",
        );
      }
      const requestId = mockUuid(MOCK_ID_SPACE.approval, 70_000 + mockDb.writtenEvents);
      const stepId = mockUuid(MOCK_ID_SPACE.approval, 80_000 + mockDb.writtenEvents);
      quotation.approval = {
        request_id: requestId,
        status: "pending",
        steps: [
          {
            id: stepId,
            seq: 1,
            role: approverRole,
            decided_role: null,
            decision: null,
            by: null,
            remark: null,
            decided_at: null,
          },
        ],
        request_remark: parsed.data.remark ?? null,
      };
      refreshGate(quotation);
      // Waits in the approver's inbox (APPR-001) until a manager decides it.
      mockDb.approvalSteps.push({
        stepId,
        requestId,
        seq: 1,
        role: approverRole,
        stalled: false,
        docType: "quotation",
        docId: quotation.id,
        number: null,
        partyName: quotation.party.name,
        total: quotation.totals.total,
        isProvisional: quotation.is_provisional,
        discountPct: quotation.discount?.effective_pct ?? null,
        raisedBy: MOCK_CREATOR ?? null,
        raisedAt: new Date().toISOString(),
        decision: null,
        remark: null,
        decidedAt: null,
        closed: null,
      });
      recordQuotationEvent(quotation, "quotation.approval_requested", {
        role: approverRole,
        remark: parsed.data.remark ?? null,
      });
      mockDb.quotationWrites.set(replay.key, {
        body: replay.serialized,
        quotationId: quotation.id,
      });
      return HttpResponse.json({ data: quotation });
    },
  ),

  http.post(buildApiUrl("/quotations/:quotationId/transition"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw);
    if (replay.kind === "respond") return replay.response;

    const parsed = z
      .object({
        to: z.enum(QUOTATION_ANSWERS),
        remark: remarkSchema,
        expected_status: z.string().optional(),
      })
      .safeParse(raw);
    if (!parsed.success) {
      return validation({ to: "accepted, rejected or negotiation" });
    }
    const found = findQuotation(String(params.quotationId));
    if (found === undefined) {
      return errorResponse(404, "not_found", "No such quotation.");
    }
    const quotation = settle(found);
    const { to, remark, expected_status: expected } = parsed.data;
    if (expected !== undefined && expected !== quotation.status) {
      return errorResponse(409, "status_changed", "The quotation has moved on.", {
        status: quotation.status,
      });
    }
    if (quotation.superseded_by !== null) {
      return errorResponse(
        409,
        "quotation_superseded",
        `Version ${String(quotation.superseded_by.version)} replaced this one.`,
      );
    }
    if (
      !ANSWERABLE_STATUSES.includes(quotation.status) ||
      (to === "negotiation" && quotation.status === "negotiation")
    ) {
      return errorResponse(
        409,
        "invalid_transition",
        `A ${quotation.status} quotation can't be marked ${to}.`,
      );
    }
    if (quotation.valid_until !== null && quotation.valid_until < today()) {
      return errorResponse(422, "quotation_expired", "The quotation is past its validity.");
    }
    const closed = leadNotOpen(quotation);
    if (closed !== null) return closed;

    const from = quotation.status;
    const now = new Date().toISOString();
    quotation.status = to;
    quotation.updated_at = now;
    if (to === "accepted" || to === "rejected") {
      quotation.accepted_at = to === "accepted" ? now : null;
      quotation.rejected_at = to === "rejected" ? now : null;
      quotation.decided_by = MOCK_CREATOR ?? null;
      quotation.decision_remark = remark ?? null;
    }
    recordQuotationEvent(quotation, `quotation.${to}`, { from, to, remark: remark ?? null });
    if (to === "accepted") {
      moveLead(quotation, "won");
    } else if (to === "negotiation" && leadOf(quotation)?.stage === "quoted") {
      moveLead(quotation, "negotiation");
    }
    mockDb.quotationWrites.set(replay.key, { body: replay.serialized, quotationId: quotation.id });
    return HttpResponse.json({ data: quotation });
  }),

  http.post(buildApiUrl("/quotations/:quotationId/revise"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const raw: unknown = await request.json();
    const replay = replayWrite(request, raw, 201);
    if (replay.kind === "respond") return replay.response;

    const parsed = z
      .object({
        price_effective_date: z.string().nullish(),
        expected_status: z.string().optional(),
      })
      .safeParse(raw);
    if (!parsed.success) {
      return validation({ price_effective_date: "a date" });
    }
    const found = findQuotation(String(params.quotationId));
    if (found === undefined) {
      return errorResponse(404, "not_found", "No such quotation.");
    }
    const quotation = settle(found);
    const expected = parsed.data.expected_status;
    if (expected !== undefined && expected !== quotation.status) {
      return errorResponse(409, "status_changed", "The quotation has moved on.", {
        status: quotation.status,
      });
    }
    if (quotation.superseded_by !== null) {
      return errorResponse(409, "quotation_superseded", "Revise the current version.");
    }
    if (!REVISABLE_STATUSES.includes(quotation.status)) {
      return errorResponse(
        409,
        "invalid_transition",
        quotation.status === "draft"
          ? "A draft is edited, not revised."
          : "An accepted quotation is not revised.",
      );
    }
    const open = mockDb.quotations.find(
      (item) => item.supersedes?.id === quotation.id && item.status === "draft",
    );
    if (open !== undefined) {
      return errorResponse(
        409,
        "revision_exists",
        `Version ${String(open.version)} is already being drafted; open it instead.`,
      );
    }
    const lead = leadOf(quotation);
    if (lead === undefined) {
      return errorResponse(404, "not_found", "The quotation's lead is out of sight.");
    }

    let repriced = 0;
    const lines = quotation.lines.flatMap((line) => {
      const product = MOCK_PRODUCTS.find((item) => item.id === line.product_id);
      if (product === undefined) return [];
      const priced = mockLine(
        line.line_no,
        product,
        Number(line.qty),
        [Number(line.discount_pct), Number(line.discount2_pct), Number(line.discount3_pct)],
        line.provisional_fields.length > 0,
        mockDb.priceVersion,
      );
      if (priced.rate !== line.rate || priced.gst_slab !== line.gst_slab) repriced += 1;
      return [priced];
    });
    const createdAt = new Date().toISOString();
    const base = mockDraft({
      id: mockUuid(MOCK_ID_SPACE.quotation, 60_000 + mockDb.quotations.length),
      lead,
      salesType: quotation.sales_type,
      party: quotation.party,
      terms: quotation.terms,
      lines,
      createdAt,
    });
    const revision = withLines(
      {
        ...base,
        version: quotation.version + 1,
        supersedes: { id: quotation.id, version: quotation.version },
        price_effective_date: parsed.data.price_effective_date ?? today(),
      },
      lines,
      repriced > 0
        ? [
            `repriced: ${String(repriced)} of ${String(lines.length)} lines have a new rate or tax slab`,
          ]
        : [],
    );
    mockDb.quotations.unshift(revision);
    recordQuotationEvent(quotation, "quotation.revised", {
      revision_id: revision.id,
      version: revision.version,
    });
    mockDb.quotationEvents.set(revision.id, [
      newMockEvent("quotation.created", { revises: quotation.version }),
    ]);
    mockDb.quotationWrites.set(replay.key, { body: replay.serialized, quotationId: revision.id });
    return HttpResponse.json({ data: revision }, { status: 201 });
  }),

  http.get(buildApiUrl("/quotations/:quotationId/versions"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const quotation = findQuotation(String(params.quotationId));
    if (quotation === undefined) {
      return errorResponse(404, "not_found", "No such quotation.");
    }
    const body: QuotationVersionsWire = {
      data: versionsOf(quotation).map((item) => toQuotationSummary(settle(item))),
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/quotations/:quotationId/timeline"), async ({ params, request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const found = findQuotation(String(params.quotationId));
    if (found === undefined) {
      return errorResponse(404, "not_found", "No such quotation.");
    }
    const quotation = settle(found);
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
    const events = scenario === "empty" ? [] : [...quotationEventsOf(quotation)].sort(newestFirst);
    const hasMore = offset + limit < events.length;
    const body: TimelinePageWire = {
      data: events.slice(offset, offset + limit),
      meta: { limit, next_cursor: hasMore ? encodeCursor(offset + limit) : null },
    };
    return HttpResponse.json(body);
  }),

  http.delete(buildApiUrl("/quotations/:quotationId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const key = request.headers.get("idempotency-key")?.trim() ?? "";
    if (key === "") {
      return errorResponse(
        400,
        "idempotency_key_required",
        "An Idempotency-Key header is required.",
      );
    }
    const raw: unknown = await request.json().catch(() => ({}));
    const serialized = JSON.stringify({ id: params.quotationId, body: raw });
    const replayed = mockDb.quotationDeletes.get(key);
    if (replayed !== undefined) {
      return replayed === serialized
        ? new HttpResponse(null, { status: 204 })
        : errorResponse(409, "idempotency_key_reused", "This Idempotency-Key was already used.");
    }
    const expected = z.object({ expected_status: z.string().optional() }).safeParse(raw).data;
    const draft = editableDraft(String(params.quotationId), expected?.expected_status);
    if (!draft.ok) return draft.response;

    const { quotation } = draft;
    voidApproval(quotation, "deleted");
    mockDb.quotations = mockDb.quotations.filter((item) => item.id !== quotation.id);
    const lead = leadOf(quotation);
    if (lead !== undefined) {
      recordLeadEvent(lead, "quotation.deleted", {
        quotation_id: quotation.id,
        version: quotation.version,
      });
    }
    mockDb.quotationDeletes.set(key, serialized);
    return new HttpResponse(null, { status: 204 });
  }),

  http.get(buildApiUrl("/public/q/:token"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const found = sharedQuotation(String(params.token));
    if (found === undefined) {
      return errorResponse(404, "not_found", "Unknown link.");
    }
    const quotation = settle(found);
    const body: PublicQuotationWire = {
      data: {
        quote_no: quotation.quote_no ?? "",
        version: quotation.version,
        status: quotation.status,
        sales_type: quotation.sales_type,
        seller: {
          legal_name: quotation.seller_gstin.legal_name,
          gstin: quotation.seller_gstin.gstin,
        },
        sent_at: quotation.sent_at,
        valid_until: quotation.valid_until,
        expired:
          quotation.status === "expired" ||
          (quotation.valid_until !== null && quotation.valid_until < today()),
        superseded: quotation.superseded_by !== null,
        totals: quotation.totals,
        line_count: quotation.lines.length,
        pdf_ready: quotation.pdf_state === "ready",
        pdf_url: `/public/q/${String(params.token)}/pdf`,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/public/q/:token/pdf"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const found = sharedQuotation(String(params.token));
    if (found === undefined) {
      return errorResponse(404, "not_found", "Unknown link.");
    }
    const quotation = settle(found);
    if (quotation.pdf_state !== "ready") {
      return errorResponse(409, "pdf_pending", "The PDF is not ready yet.");
    }
    // The customer's tap is the view: the first open moves a sent quotation to viewed.
    const now = new Date().toISOString();
    quotation.open_count += 1;
    quotation.viewed_at ??= now;
    if (quotation.status === "sent") {
      quotation.status = "viewed";
    }
    recordQuotationEvent(quotation, "quotation.viewed", { open_count: quotation.open_count });
    const filename = `${(quotation.quote_no ?? "quotation").replace(/\//g, "-")}-v${String(quotation.version)}.pdf`;
    // TODO(QUOT-012): the mock has no PDFs; the backend redirects to a signed storage URL.
    return new HttpResponse(null, {
      status: 302,
      headers: { Location: `https://files.polysil.example/quotations/${filename}` },
    });
  }),

  http.get(buildApiUrl("/quotations/:quotationId"), async ({ params }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const found = findQuotation(String(params.quotationId));
    if (found === undefined) {
      return errorResponse(404, "not_found", "No such quotation.");
    }
    const quotation = settle(found);
    if (scenario === "contract") {
      return HttpResponse.json({ data: { ...quotation, totals: null } });
    }
    return HttpResponse.json({ data: quotation });
  }),

  http.get(buildApiUrl("/quotations/:quotationId/pdf"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const quotation = mockDb.quotations.find((item) => item.id === params.quotationId);
    if (quotation === undefined || quotation.status === "draft") {
      return errorResponse(404, "not_found", "A draft has no PDF.");
    }
    if (quotation.pdf_state === "pending") {
      return errorResponse(409, "pdf_pending", "The PDF is still being prepared.");
    }
    if (quotation.pdf_state === "failed") {
      return errorResponse(409, "pdf_failed", quotation.pdf_error ?? "The PDF could not be made.");
    }
    const filename = `${(quotation.quote_no ?? "quotation").replace(/\//g, "-")}-v${String(quotation.version)}.pdf`;
    const body: PdfLinkWire = {
      data: {
        // TODO(QUOT-003): the mock has no PDFs; the real link is a signed storage URL.
        url: `https://files.polysil.example/quotations/${filename}`,
        expires_at: new Date(Date.now() + PDF_LINK_MINUTES * 60 * 1000).toISOString(),
        filename,
      },
    };
    return HttpResponse.json(body);
  }),
];
