import { z } from "zod";

import { pageMetaSchema } from "@/lib/api/pagination";

/**
 * MKT-002 … MKT-004 · Marketing material ordering (FS-034; handover
 * `marketing-material-contract.md`, `docs/api/marketing-material.md`). A catalogue with today's
 * price and the company's share; an order goes straight to the District Manager over the office,
 * then the marketing team dispatches it. Money is a decimal string.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.iso.date();
const isoDateTime = z.iso.datetime({ offset: true });

export const MARKETING_ORDER_STATUSES = [
  "submitted",
  "approved",
  "rejected",
  "cancelled",
  "dispatched",
] as const;
export type MarketingOrderStatus = (typeof MARKETING_ORDER_STATUSES)[number];

const refSchema = z.object({ id, name: z.string().nullable() });
export type MarketingRef = z.output<typeof refSchema>;

// ── the catalogue (MKT-002) ──────────────────────────────────────────────────────

const materialWireSchema = z.object({
  id,
  code: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  unit: z.string(),
  /** Today's price; null when none is in force. */
  price: decimal.nullable(),
  company_share_pct: decimal.nullable(),
  image_url: z.string().nullish(),
  is_active: z.boolean(),
  /** A stand-in price: show it as indicative. */
  is_provisional: z.boolean(),
});
export type MaterialWire = z.input<typeof materialWireSchema>;

export interface Material {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string | null;
  readonly unit: string;
  readonly price: string | null;
  readonly companySharePct: string | null;
  readonly active: boolean;
  readonly provisional: boolean;
}

function toMaterial(wire: z.output<typeof materialWireSchema>): Material {
  return {
    id: wire.id,
    code: wire.code,
    name: wire.name,
    description: wire.description,
    unit: wire.unit,
    price: wire.price,
    companySharePct: wire.company_share_pct,
    active: wire.is_active,
    provisional: wire.is_provisional,
  };
}

export const materialListSchema = z
  .object({ data: z.array(materialWireSchema) })
  .transform(({ data }) => data.map(toMaterial));

export const materialResponseSchema = z
  .object({ data: materialWireSchema })
  .transform(({ data }) => toMaterial(data));

export interface MaterialCreateRequest {
  readonly code: string;
  readonly name: string;
  readonly description: string | null;
  readonly unit: string;
  readonly price: string;
  readonly company_share_pct: string;
}

export interface MaterialPatchRequest {
  readonly name?: string;
  readonly description?: string | null;
  readonly unit?: string;
  readonly price?: string;
  readonly company_share_pct?: string;
  readonly is_active?: boolean;
}

// ── orders (MKT-003, MKT-004) ────────────────────────────────────────────────────

const totalsSchema = z.object({
  value: decimal,
  company_share: decimal,
  dealer_share: decimal,
});

export interface MarketingTotals {
  readonly value: string;
  readonly companyShare: string;
  readonly dealerShare: string;
}

function toTotals(wire: z.output<typeof totalsSchema>): MarketingTotals {
  return {
    value: wire.value,
    companyShare: wire.company_share,
    dealerShare: wire.dealer_share,
  };
}

const summaryWireSchema = z.object({
  id,
  order_no: z.string(),
  status: z.enum(MARKETING_ORDER_STATUSES),
  /** Null: an office's own use, which the company pays in full. */
  partner: refSchema.nullable(),
  requested_by: refSchema,
  office: refSchema,
  totals: totalsSchema,
  is_provisional: z.boolean(),
  created_at: isoDateTime,
});

const lineWireSchema = z.object({
  id,
  material: z.object({ id, code: z.string(), name: z.string() }),
  unit: z.string(),
  qty: z.number().int(),
  price: decimal,
  value: decimal,
  company_share_pct: decimal,
  company_share: decimal,
  dealer_share: decimal,
});

const orderWireSchema = summaryWireSchema.extend({
  lines: z.array(lineWireSchema),
  remark: z.string().nullable(),
  decision: z
    .object({
      status: z.enum(["approved", "rejected"]),
      /** Null for a partner user: a dealer never sees who decided. */
      by: refSchema.nullable(),
      at: isoDateTime,
      remark: z.string().nullable(),
    })
    .nullable(),
  dispatch: z
    .object({
      dispatched_on: isoDate,
      reference: z.string(),
      by: refSchema.nullable(),
    })
    .nullable(),
  cancel_remark: z.string().nullable(),
  /** Which buttons this caller may use now. */
  can: z.object({
    approve: z.boolean(),
    reject: z.boolean(),
    cancel: z.boolean(),
    dispatch: z.boolean(),
  }),
});
export type MarketingOrderWire = z.input<typeof orderWireSchema>;

export interface MarketingOrderSummary {
  readonly id: string;
  readonly orderNo: string;
  readonly status: MarketingOrderStatus;
  readonly partner: MarketingRef | null;
  readonly requestedBy: MarketingRef;
  readonly office: MarketingRef;
  readonly totals: MarketingTotals;
  readonly provisional: boolean;
  readonly createdAt: string;
}

export interface MarketingLine {
  readonly id: string;
  readonly material: { readonly id: string; readonly code: string; readonly name: string };
  readonly unit: string;
  readonly qty: number;
  readonly price: string;
  readonly value: string;
  readonly companySharePct: string;
  readonly companyShare: string;
  readonly dealerShare: string;
}

export interface MarketingOrder extends MarketingOrderSummary {
  readonly lines: readonly MarketingLine[];
  readonly remark: string | null;
  readonly decision: {
    readonly status: "approved" | "rejected";
    readonly by: MarketingRef | null;
    readonly at: string;
    readonly remark: string | null;
  } | null;
  readonly dispatch: {
    readonly dispatchedOn: string;
    readonly reference: string;
    readonly by: MarketingRef | null;
  } | null;
  readonly cancelRemark: string | null;
  readonly can: {
    readonly approve: boolean;
    readonly reject: boolean;
    readonly cancel: boolean;
    readonly dispatch: boolean;
  };
}

function toSummary(wire: z.output<typeof summaryWireSchema>): MarketingOrderSummary {
  return {
    id: wire.id,
    orderNo: wire.order_no,
    status: wire.status,
    partner: wire.partner,
    requestedBy: wire.requested_by,
    office: wire.office,
    totals: toTotals(wire.totals),
    provisional: wire.is_provisional,
    createdAt: wire.created_at,
  };
}

function toOrder(wire: z.output<typeof orderWireSchema>): MarketingOrder {
  return {
    ...toSummary(wire),
    lines: wire.lines.map((line) => ({
      id: line.id,
      material: line.material,
      unit: line.unit,
      qty: line.qty,
      price: line.price,
      value: line.value,
      companySharePct: line.company_share_pct,
      companyShare: line.company_share,
      dealerShare: line.dealer_share,
    })),
    remark: wire.remark,
    decision: wire.decision,
    dispatch:
      wire.dispatch === null
        ? null
        : {
            dispatchedOn: wire.dispatch.dispatched_on,
            reference: wire.dispatch.reference,
            by: wire.dispatch.by,
          },
    cancelRemark: wire.cancel_remark,
    can: wire.can,
  };
}

export const marketingOrderResponseSchema = z
  .object({ data: orderWireSchema })
  .transform(({ data }) => toOrder(data));

export const marketingOrderPageSchema = z
  .object({ data: z.array(summaryWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({ items: data.map(toSummary), nextCursor: meta.nextCursor }));
export type MarketingOrderPage = z.output<typeof marketingOrderPageSchema>;

/** Which orders a list shows: the views map onto the backend's filters. */
export const ORDER_VIEWS = ["mine", "awaiting", "dispatch", "all"] as const;
export type OrderView = (typeof ORDER_VIEWS)[number];

export interface MarketingOrderListParams {
  readonly view: OrderView;
}

export interface MarketingOrderCreateRequest {
  /** Staff: the dealer, or null for the office's own use. Ignored for a partner user. */
  readonly partner_id: string | null;
  readonly lines: readonly { readonly material_id: string; readonly qty: number }[];
  readonly remark: string | null;
}

export type MarketingAction = "approve" | "reject" | "cancel";

export interface DispatchRequest {
  readonly dispatched_on: string;
  readonly reference: string;
}
