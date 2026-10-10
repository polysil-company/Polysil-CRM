import { z } from "zod";

import { LEAD_STAGES } from "@/features/leads/api/leads.schemas";
import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";
import { EMPTY_VALUE, normalizeIndianMobile } from "@/lib/format";

/**
 * Quotations contract (QUOT-001 … QUOT-003), from the backend's `Quotation`,
 * `QuotationSummary`, `QuotationPage` and `PdfLink` (backend/api/schemas/quotations.py,
 * backend/docs/handover/quotations-api-contract.md).
 *
 * Money is a decimal string at two places, rates and percentages at three. The screen
 * prints what the backend sends and never computes a total: every figure the document
 * prints is in the response.
 */

export const QUOTATION_STATUSES = [
  "draft",
  "sent",
  "viewed",
  "negotiation",
  "accepted",
  "rejected",
  "expired",
] as const;
export type QuotationStatus = (typeof QUOTATION_STATUSES)[number];

export const SALES_TYPES = [
  "commercial",
  "industrial",
  "export",
  "subsidised",
  "marketing",
  "sample",
] as const;
export type SalesType = (typeof SALES_TYPES)[number];

export const PDF_STATES = ["pending", "ready", "failed"] as const;
export type PdfState = (typeof PDF_STATES)[number];

const isoDateTime = z.iso.datetime({ offset: true });
const isoDate = z.iso.date();
/** A plain decimal string: "1667.50", "2.500", "-12.00". */
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
/**
 * A name the backend does not guarantee non-empty (an office, a territory, a price list, the
 * seller's block): a blank one prints "—" instead of failing the whole quotation.
 */
const displayText = z.string().transform((value) => (value.trim() === "" ? EMPTY_VALUE : value));
const ref = z.object({ id: z.string().min(1), name: displayText });
const userRef = z.object({ id: z.string().min(1), full_name: z.string() });
const territoryRef = ref.extend({ level: displayText });
const versionRef = z.object({ id: z.string().min(1), version: z.number().int().positive() });
const leadRef = z.object({
  id: z.string().min(1),
  inquiry_no: z.string().min(1),
  stage: z.enum(LEAD_STAGES),
});
const partnerRef = z.object({
  id: z.string().min(1),
  name: z.string().nullish(),
  partner_type: z.string().nullish(),
});

const totalsSchema = z.object({
  gross: decimal,
  discount: decimal,
  taxable: decimal,
  cgst: decimal,
  sgst: decimal,
  igst: decimal,
  total: decimal,
});

function toUser(wire: z.output<typeof userRef> | null): { id: string; name: string } | null {
  return wire === null ? null : { id: wire.id, name: wire.full_name.trim() || "Unknown" };
}

function toPartner(
  wire: z.output<typeof partnerRef> | null,
): { id: string; name: string; partnerType: string | null } | null {
  return wire === null
    ? null
    : { id: wire.id, name: wire.name ?? "Channel partner", partnerType: wire.partner_type ?? null };
}

// ── list rows (QUOT-001) ──────────────────────────────────────────────────────

const quotationSummaryWireSchema = z.object({
  id: z.string().min(1),
  /** Null while draft; allocated at send. A revision keeps its predecessor's number. */
  quote_no: z.string().min(1).nullable(),
  version: z.number().int().positive(),
  status: z.enum(QUOTATION_STATUSES),
  sales_type: z.enum(SALES_TYPES),
  /** Null when the lead is deleted or outside the caller's lead scope. */
  lead: leadRef.nullable(),
  party_name: z.string().min(1),
  party_mobile: z.string(),
  partner: partnerRef.nullable(),
  owner: userRef.nullable(),
  totals: totalsSchema,
  is_provisional: z.boolean(),
  valid_until: isoDate.nullable(),
  sent_at: isoDateTime.nullable(),
  viewed_at: isoDateTime.nullable(),
  pdf_state: z.enum(PDF_STATES).nullable(),
  superseded_by: versionRef.nullable(),
  created_at: isoDateTime,
  /** A discount request on this draft waits for a manager; absent before the backend's #30. */
  awaiting_approval: z.boolean().optional(),
});

export type QuotationSummaryWire = z.input<typeof quotationSummaryWireSchema>;

export const quotationSummarySchema = quotationSummaryWireSchema.transform((wire) => ({
  id: wire.id,
  quoteNo: wire.quote_no,
  version: wire.version,
  status: wire.status,
  salesType: wire.sales_type,
  lead:
    wire.lead === null
      ? null
      : { id: wire.lead.id, code: wire.lead.inquiry_no, stage: wire.lead.stage },
  partyName: wire.party_name,
  partyMobile: wire.party_mobile,
  partner: toPartner(wire.partner),
  owner: toUser(wire.owner),
  totals: wire.totals,
  isProvisional: wire.is_provisional,
  validUntil: wire.valid_until,
  sentAt: wire.sent_at,
  viewedAt: wire.viewed_at,
  pdfState: wire.pdf_state,
  supersededBy: wire.superseded_by,
  createdAt: wire.created_at,
  awaitingApproval: wire.awaiting_approval ?? false,
}));

export type QuotationSummary = z.output<typeof quotationSummarySchema>;

/** GET /quotations — one row at a time, so one odd row never blanks the page. */
export const quotationPageSchema = cursorPageSchema(quotationSummarySchema);
export type QuotationPage = CursorPage<QuotationSummary>;
export type QuotationPageWire = { data: QuotationSummaryWire[]; meta: PageMetaWire };

/** The backend allows up to 100 rows a page. */
export const QUOTATION_PAGE_SIZES = [25, 50, 100] as const;

export interface QuotationListParams {
  readonly cursor: string | null;
  readonly pageSize: number;
  readonly q: string;
  readonly status: readonly QuotationStatus[];
  readonly salesType: SalesType | null;
  /** On by default: older versions of a revised number are hidden. */
  readonly currentOnly: boolean;
  /** Quotations on one lead, and on leads merged into it. */
  readonly leadId: string | null;
  /** Ask for the matching total ("1–25 of 49"). It costs the backend a count; off where unused. */
  readonly countTotal?: boolean;
}

// ── the document (QUOT-002) ───────────────────────────────────────────────────

const quotationLineWireSchema = z.object({
  line_no: z.number().int().positive(),
  product_id: z.string().min(1),
  description: z.string().min(1),
  hsn_code: z.string(),
  uom: z.string(),
  qty: decimal,
  rate: decimal,
  gross: decimal,
  discount_pct: decimal,
  discount1_amt: decimal,
  after_discount1: decimal,
  discount2_pct: decimal,
  discount2_amt: decimal,
  after_discount2: decimal,
  discount3_pct: decimal,
  discount3_amt: decimal,
  discount: decimal,
  taxable: decimal,
  gst_slab: decimal,
  cgst_rate: decimal,
  sgst_rate: decimal,
  igst_rate: decimal,
  cgst: decimal,
  sgst: decimal,
  igst: decimal,
  total: decimal,
  price_list_id: z.string(),
  price_list_item_id: z.string(),
  gst_rate_id: z.string(),
  /** Which figures are stand-ins ("rate", "gst_slab"): the PDF prints an INDICATIVE banner. */
  provisional_fields: z.array(z.string()),
});

export type QuotationLineWire = z.input<typeof quotationLineWireSchema>;

interface DiscountTier {
  readonly pct: string;
  readonly amount: string;
  /** The balance after this tier; after the third it is the taxable value. */
  readonly after: string;
}

interface TaxPart {
  readonly rate: string;
  readonly amount: string;
}

/** One line's printed figures, in print order. Every figure is the backend's. */
export interface QuotationLine {
  readonly lineNo: number;
  readonly productId: string;
  readonly description: string;
  readonly hsnCode: string;
  readonly uom: string;
  readonly qty: string;
  readonly rate: string;
  readonly gross: string;
  readonly discounts: readonly [DiscountTier, DiscountTier, DiscountTier];
  readonly discount: string;
  readonly taxable: string;
  readonly gstSlab: string;
  readonly cgst: TaxPart;
  readonly sgst: TaxPart;
  readonly igst: TaxPart;
  readonly total: string;
  /** From the price list and tax rate that priced it; a save sends them back to be compared. */
  readonly priceListItemId: string;
  readonly gstRateId: string;
  readonly provisionalFields: readonly string[];
}

/** The printed figures of one line, shared by a saved quotation and the pricing preview. */
function toLine(
  wire: Omit<z.output<typeof quotationLineWireSchema>, "line_no">,
  lineNo: number,
): QuotationLine {
  return {
    lineNo,
    productId: wire.product_id,
    description: wire.description,
    hsnCode: wire.hsn_code,
    uom: wire.uom,
    qty: wire.qty,
    rate: wire.rate,
    gross: wire.gross,
    discounts: [
      { pct: wire.discount_pct, amount: wire.discount1_amt, after: wire.after_discount1 },
      { pct: wire.discount2_pct, amount: wire.discount2_amt, after: wire.after_discount2 },
      { pct: wire.discount3_pct, amount: wire.discount3_amt, after: wire.taxable },
    ],
    discount: wire.discount,
    taxable: wire.taxable,
    gstSlab: wire.gst_slab,
    cgst: { rate: wire.cgst_rate, amount: wire.cgst },
    sgst: { rate: wire.sgst_rate, amount: wire.sgst },
    igst: { rate: wire.igst_rate, amount: wire.igst },
    total: wire.total,
    priceListItemId: wire.price_list_item_id,
    gstRateId: wire.gst_rate_id,
    provisionalFields: wire.provisional_fields,
  };
}

const quotationLineSchema = quotationLineWireSchema.transform((wire) => toLine(wire, wire.line_no));

/** What Send will do with a draft's discount (DiscountInfo.send_gate). */
export const SEND_GATES = [
  "none_needed",
  "required",
  "pending",
  "approved",
  "void",
  "returned",
] as const;
export type SendGate = (typeof SEND_GATES)[number];

export const APPROVAL_STATUSES = ["pending", "approved", "rejected", "cancelled"] as const;

const approvalWireSchema = z.object({
  request_id: z.string().min(1),
  status: z.enum(APPROVAL_STATUSES),
  steps: z.array(
    z.object({
      id: z.string().min(1),
      seq: z.number().int(),
      role: z.string().min(1),
      decided_role: z.string().nullish(),
      decision: z.enum(["approve", "reject"]).nullish(),
      by: userRef.nullish(),
      remark: z.string().nullish(),
      decided_at: isoDateTime.nullish(),
    }),
  ),
  request_remark: z.string().nullish(),
});

export const quotationWireSchema = z.object({
  id: z.string().min(1),
  quote_no: z.string().min(1).nullable(),
  version: z.number().int().positive(),
  status: z.enum(QUOTATION_STATUSES),
  sales_type: z.enum(SALES_TYPES),
  source: z.enum(["internal", "external"]),
  lead: leadRef.nullable(),
  party: z.object({
    name: z.string().min(1),
    mobile: z.string(),
    address: z.string().nullish(),
    gstin: z.string().nullish(),
  }),
  partner: partnerRef.nullable(),
  owner: userRef.nullable(),
  owner_org_unit: ref,
  territory: territoryRef,
  seller_gstin: z.object({
    id: z.string().min(1),
    gstin: displayText,
    legal_name: displayText,
    address: z.string().nullish(),
    state: displayText,
  }),
  place_of_supply: z.object({ territory: territoryRef, state: displayText }),
  intra_state: z.boolean(),
  price_effective_date: isoDate,
  /** Null when the lines drew from more than one list; `price_list_ids` names them all. */
  price_list: ref.nullable(),
  price_list_ids: z.array(z.string()),
  lines: z.array(quotationLineSchema),
  totals: totalsSchema,
  is_provisional: z.boolean(),
  /** Each is "code: sentence". */
  warnings: z.array(z.string()),
  terms: z.string().nullable(),
  valid_until: isoDate.nullable(),
  sent_at: isoDateTime.nullable(),
  viewed_at: isoDateTime.nullable(),
  open_count: z.number().int().nonnegative(),
  accepted_at: isoDateTime.nullable(),
  rejected_at: isoDateTime.nullable(),
  decided_by: userRef.nullable(),
  decision_remark: z.string().nullable(),
  supersedes: versionRef.nullable(),
  superseded_by: versionRef.nullable(),
  share_url: z.string().nullable(),
  pdf_state: z.enum(PDF_STATES).nullable(),
  pdf_error: z.string().nullable(),
  discount: z
    .object({
      effective_pct: decimal,
      owner_limit_pct: decimal.nullable(),
      approval_required: z.boolean(),
      send_gate: z.enum(SEND_GATES),
    })
    .nullish(),
  approval: approvalWireSchema.nullish(),
  created_at: isoDateTime,
  created_by: userRef.nullable(),
  updated_at: isoDateTime,
});

export type QuotationWire = z.input<typeof quotationWireSchema>;

export const quotationSchema = quotationWireSchema.transform((wire) => ({
  id: wire.id,
  quoteNo: wire.quote_no,
  version: wire.version,
  status: wire.status,
  salesType: wire.sales_type,
  source: wire.source,
  lead:
    wire.lead === null
      ? null
      : { id: wire.lead.id, code: wire.lead.inquiry_no, stage: wire.lead.stage },
  party: {
    name: wire.party.name,
    mobile: wire.party.mobile,
    address: wire.party.address ?? null,
    gstin: wire.party.gstin ?? null,
  },
  partner: toPartner(wire.partner),
  owner: toUser(wire.owner),
  ownerOrgUnit: wire.owner_org_unit,
  territory: wire.territory,
  seller: {
    gstin: wire.seller_gstin.gstin,
    legalName: wire.seller_gstin.legal_name,
    address: wire.seller_gstin.address ?? null,
    state: wire.seller_gstin.state,
  },
  placeOfSupply: { territory: wire.place_of_supply.territory, state: wire.place_of_supply.state },
  intraState: wire.intra_state,
  priceEffectiveDate: wire.price_effective_date,
  priceList: wire.price_list,
  lines: wire.lines,
  totals: wire.totals,
  isProvisional: wire.is_provisional,
  warnings: wire.warnings,
  terms: wire.terms,
  validUntil: wire.valid_until,
  sentAt: wire.sent_at,
  viewedAt: wire.viewed_at,
  openCount: wire.open_count,
  acceptedAt: wire.accepted_at,
  rejectedAt: wire.rejected_at,
  decidedBy: toUser(wire.decided_by),
  decisionRemark: wire.decision_remark,
  supersedes: wire.supersedes,
  supersededBy: wire.superseded_by,
  shareUrl: wire.share_url,
  pdfState: wire.pdf_state,
  pdfError: wire.pdf_error,
  /** On a draft: the discount against the owner's limit, and what Send will do. */
  discount:
    wire.discount === null || wire.discount === undefined
      ? null
      : {
          effectivePct: wire.discount.effective_pct,
          ownerLimitPct: wire.discount.owner_limit_pct,
          approvalRequired: wire.discount.approval_required,
          sendGate: wire.discount.send_gate,
        },
  /** The latest discount approval request, or null. A dealer sees no names or remarks. */
  approval:
    wire.approval === null || wire.approval === undefined
      ? null
      : {
          status: wire.approval.status,
          requestRemark: wire.approval.request_remark ?? null,
          steps: wire.approval.steps.map((step) => ({
            id: step.id,
            role: step.role,
            decidedRole: step.decided_role ?? null,
            decision: step.decision ?? null,
            by: toUser(step.by ?? null),
            remark: step.remark ?? null,
            decidedAt: step.decided_at ?? null,
          })),
        },
  createdAt: wire.created_at,
  createdBy: toUser(wire.created_by),
}));

export type Quotation = z.output<typeof quotationSchema>;

/** GET /quotations/{id}: `{ data: Quotation }`. */
export const quotationResponseSchema = z
  .object({ data: quotationSchema })
  .transform(({ data }) => data);

// ── the PDF (QUOT-003) ────────────────────────────────────────────────────────

/** GET /quotations/{id}/pdf — a signed URL, valid ten minutes. */
export const pdfLinkResponseSchema = z
  .object({
    data: z.object({
      url: z.string().min(1),
      expires_at: isoDateTime,
      filename: z.string().min(1),
    }),
  })
  .transform(({ data }) => ({
    url: data.url,
    expiresAt: data.expires_at,
    filename: data.filename,
  }));

export type PdfLink = z.output<typeof pdfLinkResponseSchema>;
export type PdfLinkWire = z.input<typeof pdfLinkResponseSchema>;

// ── the builder (QUOT-004, QUOT-005, MSTR-003) ────────────────────────────────

/** GET /products — the picker's rows. The rate is not here: the pricing preview gives it. */
export const productPageSchema = z
  .object({
    data: z.array(
      z.object({
        id: z.string().min(1),
        item_code: z.string().nullable(),
        description: z.string().min(1),
        uom: z.string().min(1),
        /** Decimal places the unit admits: a NOS. item cannot be 1.5. */
        uom_decimals: z.number().int().nonnegative(),
        hsn_code: z.string().nullable(),
        gst_slab: z.string().nullable(),
        pack_multiple: z.string().nullable(),
        is_active: z.boolean(),
      }),
    ),
    meta: z.object({ page: z.number().int(), limit: z.number().int(), total: z.number().int() }),
  })
  .transform(({ data, meta }) => ({
    items: data.map((wire) => ({
      id: wire.id,
      code: wire.item_code,
      description: wire.description,
      uom: wire.uom,
      uomDecimals: wire.uom_decimals,
      hsnCode: wire.hsn_code,
      gstSlab: wire.gst_slab,
      packMultiple: wire.pack_multiple,
    })),
    total: meta.total,
  }));

export type ProductPick = z.output<typeof productPageSchema>["items"][number];
export type ProductPageWire = z.input<typeof productPageSchema>;

/** POST /pricing/quote-lines request, as the backend reads it. */
export interface QuoteLinesRequest {
  readonly place_of_supply_territory_id: string;
  readonly lines: readonly {
    readonly product_id: string;
    readonly qty: string;
    readonly discount_pct: string;
    readonly discount2_pct: string;
    readonly discount3_pct: string;
  }[];
  readonly as_of?: string;
  readonly partner_id?: string;
}

const previewLineWireSchema = quotationLineWireSchema.omit({ line_no: true });

/** POST /pricing/quote-lines — every printed figure of every line, and the totals. */
export const quotePreviewResponseSchema = z
  .object({
    data: z.object({
      as_of: isoDate,
      intra_state: z.boolean(),
      price_list_ids: z.array(z.string()),
      lines: z.array(previewLineWireSchema),
      totals: totalsSchema,
      warnings: z.array(z.string()),
    }),
  })
  .transform(({ data }) => ({
    asOf: data.as_of,
    intraState: data.intra_state,
    lines: data.lines.map((line, index) => toLine(line, index + 1)),
    totals: data.totals,
    warnings: data.warnings,
  }));

export type QuotePreview = z.output<typeof quotePreviewResponseSchema>;
export type QuotePreviewWire = z.input<typeof quotePreviewResponseSchema>;

/** A saved line: what the preview priced, with the ids a save re-resolves and compares. */
export interface QuotationLineRequest {
  readonly product_id: string;
  readonly qty: string;
  readonly discount_pct: string;
  readonly discount2_pct: string;
  readonly discount3_pct: string;
  readonly price_list_item_id?: string;
  readonly gst_rate_id?: string;
}

/** The party printed on the quotation; defaults from the lead. */
export interface PartyRequest {
  readonly name: string;
  readonly mobile: string;
  readonly address: string | null;
  readonly gstin: string | null;
}

/** POST /quotations — a draft on a lead. Fields left out default from the lead. */
export interface CreateQuotationRequest {
  readonly lead_id: string;
  readonly sales_type: SalesType;
  readonly party: PartyRequest;
  readonly terms: string | null;
  readonly lines: readonly QuotationLineRequest[];
}

/** PATCH /quotations/{id} — a draft's header; the response re-prices the lines. */
export interface PatchQuotationRequest {
  readonly sales_type?: SalesType;
  readonly party?: PartyRequest;
  readonly terms?: string | null;
  readonly expected_status: "draft";
}

/** PUT /quotations/{id}/lines — the whole basket, in order. */
export interface ReplaceLinesRequest {
  readonly lines: readonly QuotationLineRequest[];
  readonly expected_status: "draft";
}

/** The sales types the backend prices today; the rest answer `sales_type_unsupported`. */
export const PRICED_SALES_TYPES = [
  "commercial",
  "industrial",
] as const satisfies readonly SalesType[];

/** The builder's header form. */
export const quotationHeaderFormSchema = z.object({
  salesType: z.enum(PRICED_SALES_TYPES),
  partyName: z.string().trim().min(1, { message: "Enter who the quotation is for" }).max(200),
  partyMobile: z
    .string()
    .trim()
    .refine((value) => normalizeIndianMobile(value) !== null, {
      message: "Enter a 10-digit Indian mobile number",
    }),
  partyAddress: z.string().trim().max(500, { message: "Keep the address under 500 characters" }),
  partyGstin: z
    .string()
    .trim()
    .regex(/^$|^[0-9]{2}[A-Za-z]{5}[0-9]{4}[A-Za-z][0-9A-Za-z]{3}$/, {
      message: "A GSTIN is 15 characters, like 24AAACP1234A1Z5",
    }),
  terms: z.string().trim().max(2000, { message: "Keep the terms under 2,000 characters" }),
});

export type QuotationHeaderForm = z.infer<typeof quotationHeaderFormSchema>;

// ── the lifecycle (QUOT-006 … QUOT-011) ───────────────────────────────────────

/** POST /quotations/{id}/send. `none`: no message; the officer shares the link. */
export interface SendQuotationRequest {
  readonly channel: "whatsapp" | "none";
  readonly expected_status: "draft";
}

/** POST /quotations/{id}/request-approval. */
export interface RequestApprovalRequest {
  readonly remark: string | null;
}

/** The customer's answers a sent quotation can record. */
export const QUOTATION_ANSWERS = ["accepted", "negotiation", "rejected"] as const;
export type QuotationAnswer = (typeof QUOTATION_ANSWERS)[number];

/** POST /quotations/{id}/transition. */
export interface TransitionQuotationRequest {
  readonly to: QuotationAnswer;
  readonly remark: string | null;
  readonly expected_status: QuotationStatus;
}

/** POST /quotations/{id}/revise — today's prices unless a date is given. */
export interface ReviseQuotationRequest {
  readonly price_effective_date: string | null;
  readonly expected_status: QuotationStatus;
}

/** DELETE /quotations/{id} — drafts only. */
export interface DeleteQuotationRequest {
  readonly expected_status: "draft";
}

/** GET /quotations/{id}/versions — every version of the number, oldest first. */
export const quotationVersionsResponseSchema = z
  .object({ data: z.array(quotationSummarySchema) })
  .transform(({ data }) => data);
export type QuotationVersionsWire = z.input<typeof quotationVersionsResponseSchema>;

/** DELETE answers 204 with no body. */
export const noContentSchema = z.undefined();

/** The longest remark the screens accept; the backend stores it as text. */
export const QUOTATION_REMARK_MAX_LENGTH = 1000;

/** A remark on an answer or an approval request; optional. */
export const quotationRemarkFormSchema = z.object({
  remark: z.string().trim().max(QUOTATION_REMARK_MAX_LENGTH, {
    message: "Keep the remark under 1,000 characters",
  }),
});
export type QuotationRemarkForm = z.infer<typeof quotationRemarkFormSchema>;

// ── the customer's page (QUOT-012) ──────────────────────────────────────────────

/**
 * GET /public/q/{token} — what a shared link shows before the PDF. No party, no mobile, no
 * lines: a link forwarded to the wrong person learns a number and a total, nothing else.
 */
export const publicQuotationResponseSchema = z
  .object({
    data: z.object({
      quote_no: z.string().min(1),
      version: z.number().int().positive(),
      status: z.enum(QUOTATION_STATUSES),
      sales_type: z.enum(SALES_TYPES),
      seller: z.object({ legal_name: displayText, gstin: displayText }),
      sent_at: isoDateTime.nullable(),
      valid_until: isoDate.nullable(),
      expired: z.boolean(),
      superseded: z.boolean(),
      totals: totalsSchema,
      line_count: z.number().int().nonnegative(),
      pdf_ready: z.boolean(),
      /**
       * `/api/v1/public/q/{token}/pdf` (older backends: `/public/q/{token}/pdf`), which records
       * the view and redirects. Used as given, never built (`asApiPath`).
       */
      pdf_url: z.string().startsWith("/"),
    }),
  })
  .transform(({ data }) => ({
    quoteNo: data.quote_no,
    version: data.version,
    status: data.status,
    salesType: data.sales_type,
    seller: { legalName: data.seller.legal_name, gstin: data.seller.gstin },
    sentAt: data.sent_at,
    validUntil: data.valid_until,
    expired: data.expired,
    superseded: data.superseded,
    totals: data.totals,
    lineCount: data.line_count,
    pdfReady: data.pdf_ready,
    pdfPath: data.pdf_url,
  }));

export type PublicQuotation = z.output<typeof publicQuotationResponseSchema>;
export type PublicQuotationWire = z.input<typeof publicQuotationResponseSchema>;
