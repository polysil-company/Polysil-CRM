import { z } from "zod";

/**
 * SO-009, CMPL-011, MSTR-017 · Warranty (FS-046; handover `warranty.md`, `docs/api/warranty.md`):
 * each dispatch starts a period from its DC date (else the dispatch day) for the months in force
 * for the product's category; a complaint reads whether its product was in warranty when raised.
 * Out of warranty never blocks anything.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.iso.date();

export const WARRANTY_STATUSES = ["active", "expired", "none", "unknown"] as const;
export type WarrantyStatus = (typeof WARRANTY_STATUSES)[number];

export const LINE_WARRANTY_STATUSES = [...WARRANTY_STATUSES, "not_dispatched"] as const;
export type LineWarrantyStatus = (typeof LINE_WARRANTY_STATUSES)[number];

export const CLAIM_WARRANTY_STATUSES = ["in_warranty", "expired", "none", "unknown"] as const;
export type ClaimWarrantyStatus = (typeof CLAIM_WARRANTY_STATUSES)[number];

// ── the order's warranty (SO-009) ────────────────────────────────────────────────

const dispatchSchema = z.object({
  dispatch_id: id,
  dispatch_no: z.string(),
  qty: decimal,
  /** The DC date, else the dispatch day in IST. */
  start: isoDate,
  start_basis: z.enum(["dc_date", "dispatched_at"]),
  /** The last covered day; null for no warranty or no term. */
  end: isoDate.nullable(),
  months: z.number().int().nullable(),
  status: z.enum(WARRANTY_STATUSES),
});

const claimSchema = z.object({
  complaint_id: id,
  complaint_no: z.string().nullable(),
  /** The complaint's own status. */
  status: z.string(),
  raised_on: isoDate.nullable(),
  defective_qty: decimal,
  warranty_status: z.enum(CLAIM_WARRANTY_STATUSES),
});

const lineSchema = z.object({
  order_line_id: id,
  product: z.object({ id, description: z.string() }),
  qty_ordered: decimal,
  qty_dispatched: decimal,
  dispatches: z.array(dispatchSchema),
  status: z.enum(LINE_WARRANTY_STATUSES),
  claims: z.array(claimSchema),
});

const orderWarrantyWireSchema = z.object({
  order_id: id,
  order_no: z.string().nullable(),
  order_type: z.string(),
  replacement_for: z.object({ complaint_id: id, complaint_no: z.string().nullable() }).nullable(),
  lines: z.array(lineSchema),
});
export type OrderWarrantyWire = z.input<typeof orderWarrantyWireSchema>;

export const orderWarrantySchema = z
  .object({ data: orderWarrantyWireSchema })
  .transform(({ data }) => ({
    orderId: data.order_id,
    replacementFor:
      data.replacement_for === null
        ? null
        : { id: data.replacement_for.complaint_id, code: data.replacement_for.complaint_no },
    lines: data.lines.map((line) => ({
      id: line.order_line_id,
      product: line.product,
      qtyOrdered: line.qty_ordered,
      qtyDispatched: line.qty_dispatched,
      status: line.status,
      dispatches: line.dispatches.map((dispatch) => ({
        id: dispatch.dispatch_id,
        dispatchNo: dispatch.dispatch_no,
        qty: dispatch.qty,
        start: dispatch.start,
        startBasis: dispatch.start_basis,
        end: dispatch.end,
        months: dispatch.months,
        status: dispatch.status,
      })),
      claims: line.claims.map((claim) => ({
        id: claim.complaint_id,
        code: claim.complaint_no,
        status: claim.status,
        raisedOn: claim.raised_on,
        defectiveQty: claim.defective_qty,
        warrantyStatus: claim.warranty_status,
      })),
    })),
  }));
export type OrderWarranty = z.output<typeof orderWarrantySchema>;
export type WarrantyLine = OrderWarranty["lines"][number];

// ── a complaint line's warranty (CMPL-011) ───────────────────────────────────────

export const complaintLineWarrantySchema = z.object({
  status: z.enum(CLAIM_WARRANTY_STATUSES),
  start: isoDate.nullable(),
  end: isoDate.nullable(),
  months: z.number().int().nullable(),
  /** Where the start came from: a dispatch, or the supply date typed on the complaint. */
  basis: z.enum(["dispatch", "supply_date"]).nullable(),
});
export type ComplaintLineWarranty = z.output<typeof complaintLineWarrantySchema>;

// ── warranty periods (MSTR-017) ──────────────────────────────────────────────────

const categoryRefSchema = z.object({ id, code: z.string(), name: z.string() });

const termWireSchema = z.object({
  id,
  /** Null: the default for every category without its own term. */
  product_category: categoryRefSchema.nullable(),
  /** 0 means no warranty. */
  months: z.number().int().min(0),
  effective_from: isoDate,
  /** First day no longer in force (exclusive); null while open. */
  effective_to: isoDate.nullable(),
});
export type WarrantyTermWire = z.input<typeof termWireSchema>;

export interface WarrantyTerm {
  readonly id: string;
  readonly category: { readonly id: string; readonly code: string; readonly name: string } | null;
  readonly months: number;
  readonly effectiveFrom: string;
  readonly effectiveTo: string | null;
}

export const warrantyTermsSchema = z
  .object({ data: z.array(termWireSchema) })
  .transform(({ data }) =>
    data.map((term): WarrantyTerm => ({
      id: term.id,
      category: term.product_category,
      months: term.months,
      effectiveFrom: term.effective_from,
      effectiveTo: term.effective_to,
    })),
  );

export interface SetWarrantyTermRequest {
  /** Null sets the default. */
  readonly product_category_id: string | null;
  /** 0 to 120; 0 means no warranty. */
  readonly months: number;
  /** Tomorrow (IST) or later. */
  readonly effective_from: string;
}

export const MAX_WARRANTY_MONTHS = 120;
