import { z } from "zod";

import { LEAD_STAGES } from "@/features/leads/api/leads.schemas";
import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

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
const ref = z.object({ id: z.string().min(1), name: z.string().min(1) });
const userRef = z.object({ id: z.string().min(1), full_name: z.string() });
const territoryRef = ref.extend({ level: z.string().min(1) });
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

const quotationLineSchema = quotationLineWireSchema.transform((wire) => ({
  lineNo: wire.line_no,
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
  provisionalFields: wire.provisional_fields,
}));

export type QuotationLine = z.output<typeof quotationLineSchema>;

const approvalWireSchema = z.object({
  request_id: z.string().min(1),
  status: z.string().min(1),
  steps: z.array(
    z.object({
      id: z.string().min(1),
      seq: z.number().int(),
      role: z.string().min(1),
      decided_role: z.string().nullish(),
      decision: z.string().nullish(),
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
    gstin: z.string().min(1),
    legal_name: z.string().min(1),
    address: z.string().nullish(),
    state: z.string().min(1),
  }),
  place_of_supply: z.object({ territory: territoryRef, state: z.string().min(1) }),
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
      send_gate: z.string().min(1),
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
