import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";
import { EMPTY_VALUE } from "@/lib/format";

/**
 * Sales orders contract (SO-001 … SO-004, DISP-002), from the backend's `Order`,
 * `OrderSummary`, `OrderPage`, `Dispatch` and their requests (backend/docs/api/orders.md,
 * backend/docs/handover/orders-api-contract.md).
 *
 * Money is a decimal string at two places, quantities at three. The screen prints what the
 * backend sends and never computes a total. Blocks the caller may not see (lead, partner,
 * owner, quotations) come back null or empty: the screen says "not visible to you".
 */

export const ORDER_STATUSES = [
  "draft",
  "submitted",
  "approved",
  "partially_dispatched",
  "dispatched",
  "closed_short",
  "cancelled",
] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export const ORDER_TYPES = [
  "commercial",
  "industrial",
  "export",
  "sample",
  "marketing_material",
  "subsidised",
  "replacement",
] as const;
export type OrderType = (typeof ORDER_TYPES)[number];

/** The types the backend accepts today; the others answer `order_type_unsupported`. */
export const ORDERABLE_TYPES = ["commercial", "industrial"] as const satisfies readonly OrderType[];

export const PAYMENT_TERMS = ["full_payment", "credit"] as const;
export type PaymentTerms = (typeof PAYMENT_TERMS)[number];

export const ORDER_PDF_STATES = ["none", "pending", "ready", "failed"] as const;
export type OrderPdfState = (typeof ORDER_PDF_STATES)[number];

const isoDateTime = z.iso.datetime({ offset: true });
const isoDate = z.iso.date();
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
/** A name the backend does not guarantee non-empty prints "—" rather than failing the order. */
const displayText = z.string().transform((value) => (value.trim() === "" ? EMPTY_VALUE : value));

const userRef = z
  .object({ id: z.string().min(1), full_name: z.string() })
  .transform((wire) => ({ id: wire.id, name: wire.full_name.trim() || "Unknown" }));
const partnerRef = z
  .object({ id: z.string().min(1), name: displayText, partner_type: z.string().nullish() })
  .transform((wire) => ({ id: wire.id, name: wire.name, partnerType: wire.partner_type ?? null }));
const territoryRef = z.object({ id: z.string().min(1), name: displayText, level: displayText });

const totalsSchema = z.object({
  gross: decimal,
  discount: decimal,
  taxable: decimal,
  cgst: decimal,
  sgst: decimal,
  igst: decimal,
  total: decimal,
});

// ── the list (SO-001) ────────────────────────────────────────────────────────────

const orderSummaryWireSchema = z.object({
  id: z.string().min(1),
  /** Null until the first submit. */
  order_no: z.string().min(1).nullable(),
  status: z.enum(ORDER_STATUSES),
  order_type: z.enum(ORDER_TYPES),
  party_name: z.string(),
  partner: partnerRef.nullable(),
  owner: userRef.nullable(),
  totals: totalsSchema,
  is_provisional: z.boolean(),
  /** Share of the ordered quantity sent, 0 to 100. */
  dispatched_pct: z.number().int().min(0).max(100),
  /** The role of the next undecided approval step. */
  approval_waiting_on: z.string().nullable(),
  submitted_at: isoDateTime.nullable(),
  created_at: isoDateTime,
});

export type OrderSummaryWire = z.input<typeof orderSummaryWireSchema>;

const orderSummarySchema = orderSummaryWireSchema.transform((wire) => ({
  id: wire.id,
  orderNo: wire.order_no,
  status: wire.status,
  orderType: wire.order_type,
  partyName: wire.party_name.trim() || "Unnamed party",
  partner: wire.partner,
  owner: wire.owner,
  totals: wire.totals,
  isProvisional: wire.is_provisional,
  dispatchedPct: wire.dispatched_pct,
  waitingOn: wire.approval_waiting_on,
  submittedAt: wire.submitted_at,
  createdAt: wire.created_at,
}));

export type OrderSummary = z.output<typeof orderSummarySchema>;

/** GET /orders — one row at a time, so one odd row never blanks the page. */
export const orderPageSchema = cursorPageSchema(orderSummarySchema);
export type OrderPage = CursorPage<OrderSummary>;
export type OrderPageWire = { data: OrderSummaryWire[]; meta: PageMetaWire };

export const ORDER_PAGE_SIZE_OPTIONS = [25, 50, 100] as const;
export const DEFAULT_ORDER_PAGE_SIZE = 25;

export interface OrderListParams {
  readonly cursor: string | null;
  readonly pageSize: number;
  readonly q: string;
  readonly status: readonly OrderStatus[];
  readonly orderType: OrderType | null;
  /** Only the user's own orders (`owner=me`). */
  readonly mine: boolean;
  readonly leadId: string | null;
}

// ── the document (SO-002) ─────────────────────────────────────────────────────────

const orderLineWireSchema = z.object({
  id: z.string().min(1),
  line_no: z.number().int().positive(),
  product_id: z.string().min(1),
  description: z.string(),
  hsn_code: z.string(),
  uom: z.string(),
  /** How many decimals the unit takes; 0 for pieces. */
  uom_decimals: z.number().int().min(0).max(3),
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
  provisional_fields: z.array(z.string()),
  qty_dispatched: decimal,
  qty_short: decimal,
  qty_open: decimal,
});

export type OrderLineWire = z.input<typeof orderLineWireSchema>;

const orderLineSchema = orderLineWireSchema.transform((wire) => ({
  id: wire.id,
  lineNo: wire.line_no,
  productId: wire.product_id,
  description: wire.description.trim() || EMPTY_VALUE,
  hsnCode: wire.hsn_code,
  uom: wire.uom,
  uomDecimals: wire.uom_decimals,
  qty: wire.qty,
  rate: wire.rate,
  gross: wire.gross,
  discounts: [
    { pct: wire.discount_pct, amount: wire.discount1_amt },
    { pct: wire.discount2_pct, amount: wire.discount2_amt },
    { pct: wire.discount3_pct, amount: wire.discount3_amt },
  ] as const,
  discount: wire.discount,
  taxable: wire.taxable,
  gstSlab: wire.gst_slab,
  cgst: { rate: wire.cgst_rate, amount: wire.cgst },
  sgst: { rate: wire.sgst_rate, amount: wire.sgst },
  igst: { rate: wire.igst_rate, amount: wire.igst },
  total: wire.total,
  provisionalFields: wire.provisional_fields,
  qtyDispatched: wire.qty_dispatched,
  qtyShort: wire.qty_short,
  qtyOpen: wire.qty_open,
}));

export type OrderLine = z.output<typeof orderLineSchema>;

const approvalStepSchema = z
  .object({
    id: z.string().min(1),
    seq: z.number().int().positive(),
    role: z.string().min(1),
    decided_role: z.string().nullish(),
    decision: z.enum(["approve", "reject"]).nullish(),
    by: userRef.nullish(),
    remark: z.string().nullish(),
    decided_at: isoDateTime.nullish(),
  })
  .transform((wire) => ({
    id: wire.id,
    seq: wire.seq,
    role: wire.role,
    decidedRole: wire.decided_role ?? null,
    decision: wire.decision ?? null,
    by: wire.by ?? null,
    remark: wire.remark ?? null,
    decidedAt: wire.decided_at ?? null,
  }));

export type OrderApprovalStep = z.output<typeof approvalStepSchema>;

const dispatchWireSchema = z.object({
  id: z.string().min(1),
  order: z.object({
    id: z.string().min(1),
    order_no: z.string().nullable(),
    party_name: z.string(),
  }),
  dispatch_no: z.string().min(1),
  dc_no: z.string().nullable(),
  dc_date: isoDate.nullable(),
  invoice_no: z.string().nullable(),
  invoice_date: isoDate.nullable(),
  dispatched_at: isoDateTime,
  transporter: z.string().nullable(),
  vehicle_no: z.string().nullable(),
  dispatched_by: userRef.nullable(),
  voided_at: isoDateTime.nullable(),
  void_remark: z.string().nullable(),
  lines: z.array(
    z.object({ order_line_id: z.string().min(1), line_no: z.number().int(), qty: decimal }),
  ),
  /** invoice_before_dc, duplicate_invoice_no: recorded anyway. */
  warnings: z.array(z.string()).optional(),
});

export type DispatchWire = z.input<typeof dispatchWireSchema>;

const dispatchSchema = dispatchWireSchema.transform((wire) => ({
  id: wire.id,
  orderId: wire.order.id,
  dispatchNo: wire.dispatch_no,
  dcNo: wire.dc_no,
  dcDate: wire.dc_date,
  invoiceNo: wire.invoice_no,
  invoiceDate: wire.invoice_date,
  dispatchedAt: wire.dispatched_at,
  transporter: wire.transporter,
  vehicleNo: wire.vehicle_no,
  dispatchedBy: wire.dispatched_by,
  voidedAt: wire.voided_at,
  voidRemark: wire.void_remark,
  lines: wire.lines.map((line) => ({
    orderLineId: line.order_line_id,
    lineNo: line.line_no,
    qty: line.qty,
  })),
  warnings: wire.warnings ?? [],
}));

export type Dispatch = z.output<typeof dispatchSchema>;

export const orderWireSchema = z.object({
  doc_type: z.literal("sales_order").optional(),
  id: z.string().min(1),
  order_no: z.string().min(1).nullable(),
  status: z.enum(ORDER_STATUSES),
  order_type: z.enum(ORDER_TYPES),
  party: z.object({
    name: z.string(),
    mobile: z.string().nullish(),
    address: z.string().nullish(),
    gstin: z.string().nullish(),
  }),
  partner: partnerRef.nullable(),
  lead: z.object({ id: z.string().min(1), inquiry_no: z.string().min(1) }).nullable(),
  quotations: z.array(
    z.object({
      id: z.string().min(1),
      quote_no: z.string().nullable(),
      version: z.number().int().positive(),
    }),
  ),
  owner: userRef.nullable(),
  owner_org_unit: z.object({ id: z.string().min(1), name: displayText }),
  territory: territoryRef,
  delivery_address: z.string().nullable(),
  payment_terms: z.enum(PAYMENT_TERMS),
  seller: z
    .object({
      gstin: displayText,
      legal_name: displayText,
      address: z.string().nullable(),
      state_code: displayText,
    })
    .nullable(),
  place_of_supply: territoryRef,
  intra_state: z.boolean(),
  price_effective_date: isoDate,
  tax_date: isoDate.nullable(),
  is_provisional: z.boolean(),
  lines: z.array(orderLineSchema),
  totals: totalsSchema,
  approval: z
    .object({
      request_id: z.string().min(1),
      status: z.enum(["pending", "approved", "rejected", "cancelled"]),
      steps: z.array(approvalStepSchema),
    })
    .nullable(),
  last_rejection: z.object({ remark: z.string(), role: z.string(), at: isoDateTime }).nullable(),
  dispatches: z.array(dispatchSchema),
  /** "code: sentence", as on a quotation. */
  warnings: z.array(z.string()),
  remarks: z.string().nullable(),
  pdf_state: z.enum(ORDER_PDF_STATES),
  pdf_error: z.string().nullish(),
  confirmation: z.enum(["queued", "no_mobile", "disabled"]).nullish(),
  submitted_at: isoDateTime.nullable(),
  approved_at: isoDateTime.nullable(),
  cancelled_at: isoDateTime.nullable(),
  cancel_remark: z.string().nullable(),
  closed_at: isoDateTime.nullable(),
  close_remark: z.string().nullable(),
  created_at: isoDateTime,
});

export type OrderWire = z.input<typeof orderWireSchema>;

export const orderSchema = orderWireSchema.transform((wire) => ({
  id: wire.id,
  orderNo: wire.order_no,
  status: wire.status,
  orderType: wire.order_type,
  party: {
    name: wire.party.name.trim() || "Unnamed party",
    mobile: wire.party.mobile ?? null,
    address: wire.party.address ?? null,
    gstin: wire.party.gstin ?? null,
  },
  partner: wire.partner,
  lead: wire.lead === null ? null : { id: wire.lead.id, code: wire.lead.inquiry_no },
  quotations: wire.quotations.map((quotation) => ({
    id: quotation.id,
    quoteNo: quotation.quote_no,
    version: quotation.version,
  })),
  owner: wire.owner,
  ownerOrgUnit: wire.owner_org_unit,
  territory: wire.territory,
  deliveryAddress: wire.delivery_address,
  paymentTerms: wire.payment_terms,
  seller:
    wire.seller === null
      ? null
      : {
          gstin: wire.seller.gstin,
          legalName: wire.seller.legal_name,
          address: wire.seller.address,
          stateCode: wire.seller.state_code,
        },
  placeOfSupply: wire.place_of_supply,
  intraState: wire.intra_state,
  priceEffectiveDate: wire.price_effective_date,
  taxDate: wire.tax_date,
  isProvisional: wire.is_provisional,
  lines: wire.lines,
  totals: wire.totals,
  approval: wire.approval,
  lastRejection: wire.last_rejection,
  dispatches: wire.dispatches,
  warnings: wire.warnings,
  remarks: wire.remarks,
  pdfState: wire.pdf_state,
  pdfError: wire.pdf_error ?? null,
  confirmation: wire.confirmation ?? null,
  submittedAt: wire.submitted_at,
  approvedAt: wire.approved_at,
  cancelledAt: wire.cancelled_at,
  cancelRemark: wire.cancel_remark,
  closedAt: wire.closed_at,
  closeRemark: wire.close_remark,
  createdAt: wire.created_at,
}));

export type Order = z.output<typeof orderSchema>;

/** GET /orders/{id} and every order-returning write: `{ data: Order }`. */
export const orderResponseSchema = z.object({ data: orderSchema }).transform(({ data }) => data);

/** POST /orders/{id}/dispatches: `{ data: Dispatch }`. */
export const dispatchResponseSchema = z
  .object({ data: dispatchSchema })
  .transform(({ data }) => data);

/** DELETE answers 204 with no body. */
export const noContentSchema = z.undefined();

// ── writes (SO-003, SO-004, DISP-002) ─────────────────────────────────────────────

/** POST /orders from accepted quotations: the order takes the rest from them. */
export interface CreateOrderFromQuotations {
  readonly order_type: (typeof ORDERABLE_TYPES)[number];
  readonly quotation_ids: readonly string[];
  readonly delivery_address: string | null;
  readonly payment_terms: PaymentTerms;
  readonly remarks: string | null;
}

/** PATCH /orders/{id} — a draft's header, as far as this screen edits it. */
export interface PatchOrderRequest {
  readonly delivery_address?: string | null;
  readonly payment_terms?: PaymentTerms;
  readonly remarks?: string | null;
  readonly expected_status: "draft";
}

export interface ExpectedStatusRequest {
  readonly expected_status: OrderStatus;
}

/** POST /orders/{id}/cancel, /close-short and /dispatches/{id}/void: a reason is required. */
export interface RemarkRequest {
  readonly remark: string;
  readonly expected_status: OrderStatus;
}

/** POST /orders/{id}/dispatches. */
export interface CreateDispatchRequest {
  readonly dc_no: string | null;
  readonly dc_date: string | null;
  readonly invoice_no: string | null;
  readonly invoice_date: string | null;
  readonly dispatched_at: string;
  readonly transporter: string | null;
  readonly vehicle_no: string | null;
  readonly lines: readonly { readonly order_line_id: string; readonly qty: string }[];
}

export const ORDER_REMARK_MAX_LENGTH = 1000;

/** A reason in a dialog: cancelling, voiding, closing short. Required. */
export const requiredRemarkFormSchema = z.object({
  remark: z
    .string()
    .trim()
    .min(1, { message: "Say why. It is kept on the order and its history." })
    .max(ORDER_REMARK_MAX_LENGTH, { message: "Keep it under 1,000 characters" }),
});
export type RequiredRemarkForm = z.infer<typeof requiredRemarkFormSchema>;

/** The draft header a person may change on this screen. */
export const orderHeaderFormSchema = z.object({
  deliveryAddress: z.string().trim().max(500, { message: "Keep the address under 500 characters" }),
  paymentTerms: z.enum(PAYMENT_TERMS),
  remarks: z.string().trim().max(2000, { message: "Keep the remarks under 2,000 characters" }),
});
export type OrderHeaderForm = z.infer<typeof orderHeaderFormSchema>;

/** The part of a line the dispatch form checks a quantity against. */
export interface DispatchableLine {
  readonly id: string;
  readonly qtyOpen: string;
  readonly uomDecimals: number;
}

const DISPATCH_TEXT_MAX = 60;

/**
 * The record-dispatch form, for one order's lines: each quantity at most what is open, in
 * the line's unit precision; at least one line sent; the time it left not in the future.
 * The backend checks the same, and answers with the same field names.
 */
const dispatchFormBaseSchema = z.object({
  dispatchedAt: z.string().min(1, { message: "When the goods left" }),
  dcNo: z.string().trim().max(DISPATCH_TEXT_MAX, { message: "Keep it under 60 characters" }),
  dcDate: z.string(),
  invoiceNo: z.string().trim().max(DISPATCH_TEXT_MAX, { message: "Keep it under 60 characters" }),
  invoiceDate: z.string(),
  transporter: z.string().trim().max(120, { message: "Keep it under 120 characters" }),
  vehicleNo: z.string().trim().max(20, { message: "Keep it under 20 characters" }),
  lines: z.array(z.object({ orderLineId: z.string().min(1), qty: z.string().trim() })),
});

export function dispatchFormSchemaFor(
  lines: readonly DispatchableLine[],
  now: () => number = Date.now,
): typeof dispatchFormBaseSchema {
  return dispatchFormBaseSchema.superRefine((form, ctx) => {
    const leftAt = Date.parse(form.dispatchedAt);
    if (Number.isNaN(leftAt)) {
      ctx.addIssue({ code: "custom", path: ["dispatchedAt"], message: "Enter a date and time" });
    } else if (leftAt > now() + 60_000) {
      ctx.addIssue({
        code: "custom",
        path: ["dispatchedAt"],
        message: "It can't be in the future",
      });
    }
    let sending = 0;
    for (const [index, entry] of form.lines.entries()) {
      if (entry.qty === "" || Number(entry.qty) === 0) {
        continue;
      }
      const line = lines.find((item) => item.id === entry.orderLineId);
      const path = ["lines", index, "qty"];
      if (!/^\d+(\.\d+)?$/.test(entry.qty)) {
        ctx.addIssue({ code: "custom", path, message: "A number, like 12 or 2.5" });
      } else if (line !== undefined) {
        const decimals = (entry.qty.split(".")[1] ?? "").replace(/0+$/, "").length;
        if (decimals > line.uomDecimals) {
          ctx.addIssue({
            code: "custom",
            path,
            message:
              line.uomDecimals === 0
                ? "Whole units only"
                : `At most ${String(line.uomDecimals)} decimals`,
          });
        } else if (Number(entry.qty) > Number(line.qtyOpen)) {
          ctx.addIssue({ code: "custom", path, message: "More than is still open" });
        }
      }
      sending += 1;
    }
    if (sending === 0) {
      ctx.addIssue({
        code: "custom",
        path: ["lines"],
        message: "Enter what left for at least one item",
      });
    }
  });
}

export type DispatchForm = z.infer<typeof dispatchFormBaseSchema>;
