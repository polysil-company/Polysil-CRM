import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  PRICED_SALES_TYPES,
  QUOTATION_STATUSES,
  SALES_TYPES,
  type PdfLinkWire,
  type ProductPageWire,
  type QuotationLineWire,
  type QuotePreviewWire,
  type QuotationPageWire,
  type QuotationStatus,
  type QuotationWire,
} from "@/features/quotations/api/quotations.schemas";
import { buildApiUrl } from "@/lib/api/url";
import {
  MOCK_PRODUCTS,
  mockDraft,
  mockLine,
  priceListItemId,
  toQuotationSummary,
  totalsOf,
} from "@/mocks/data/quotations";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * QUOT-001 … QUOT-003 · The backend's quotation reads (backend/docs/api/quotations.md): the
 * list with its filters, cursor paging and capped total; the document; and the PDF link,
 * with 404 on a draft and 409 while the PDF renders or after it failed.
 * QUOT-004, QUOT-005, MSTR-003 · The builder: product search, the pricing preview, and saving a
 * draft — create, header and lines — with the backend's refusals: lead_not_qualified,
 * sales_type_unsupported, status_changed, quotation_not_draft and rate_changed.
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
        : HttpResponse.json({ data: quotation }, { status: 201 }),
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

export const quotationHandlers = [
  http.get(buildApiUrl("/quotations"), async ({ request }) => {
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
    const replay = replayWrite(request, raw);
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
    const lead = mockDb.leads.find((item) => item.id === draft.quotation.lead?.id);
    const updated =
      lead === undefined
        ? draft.quotation
        : mockDraft({
            id: draft.quotation.id,
            lead,
            salesType: draft.quotation.sales_type,
            party: draft.quotation.party,
            terms: draft.quotation.terms,
            lines: priced.lines,
            createdAt: draft.quotation.created_at,
          });
    mockDb.quotations = mockDb.quotations.map((item) => (item.id === updated.id ? updated : item));
    mockDb.quotationWrites.set(replay.key, { body: replay.serialized, quotationId: updated.id });
    return HttpResponse.json({ data: updated });
  }),

  http.get(buildApiUrl("/quotations/:quotationId"), async ({ params }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const quotation = mockDb.quotations.find((item) => item.id === params.quotationId);
    if (quotation === undefined) {
      return errorResponse(404, "not_found", "No such quotation.");
    }
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
