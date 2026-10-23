import { z } from "zod";

import { pageMetaSchema } from "@/lib/api/pagination";

/**
 * SUBS-016 … SUBS-018 · Dealer commission and TOD, subsidy stage 18 (FS-033;
 * `backend/docs/handover/dealer-commission-contract.md`, `docs/api/dealer-commission.md`).
 * After full FP the co-ordinator records the dealer's commission; Accounts approves and pays.
 * Money and percentages are decimal strings.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.iso.date();
const isoDateTime = z.iso.datetime({ offset: true });

export const COMMISSION_STATUSES = [
  "calculated",
  "approved",
  "returned",
  "paid",
  "cancelled",
] as const;
export type CommissionStatus = (typeof COMMISSION_STATUSES)[number];

export const RATE_SYSTEM_TYPES = ["drip", "mini_sprinkler", "sprinkler"] as const;
export type RateSystemType = (typeof RATE_SYSTEM_TYPES)[number];

export const RATE_PARTNER_TYPES = ["distributor", "dealer", "sub_dealer"] as const;
export type RatePartnerType = (typeof RATE_PARTNER_TYPES)[number];

/** A person or partner as the backend names it; the name can be withheld (null). */
const nameRef = z.object({ id, name: z.string().nullable() });
export type NameRef = z.output<typeof nameRef>;

const commissionWireSchema = z.object({
  id,
  application: z.object({ id, application_no: z.string(), reg_no: z.string().nullable() }),
  partner: nameRef,
  status: z.enum(COMMISSION_STATUSES),
  cost_excl_gst: decimal,
  a_plus_b: decimal.nullable(),
  gi_fitting: decimal,
  pvc_hdpe_fitting: decimal,
  installation: decimal,
  commission_base: decimal,
  commission_pct: decimal,
  commission_amount: decimal,
  tod_base: decimal,
  tod_pct: decimal,
  tod_amount: decimal,
  total: decimal,
  remark: z.string().nullable(),
  recorded_by: nameRef,
  recorded_at: isoDateTime,
  decided_by: nameRef.nullable(),
  decided_at: isoDateTime.nullable(),
  decision_remark: z.string().nullable(),
  paid_on: isoDate.nullable(),
  payment_reference: z.string().nullable(),
});
export type CommissionWire = z.input<typeof commissionWireSchema>;

/** One commission, every figure as the server worked it out. */
export interface Commission {
  readonly id: string;
  readonly application: {
    readonly id: string;
    readonly number: string;
    readonly regNo: string | null;
  };
  readonly partner: NameRef;
  readonly status: CommissionStatus;
  readonly costExclGst: string;
  readonly aPlusB: string | null;
  readonly giFitting: string;
  readonly pvcHdpeFitting: string;
  readonly installation: string;
  readonly commissionBase: string;
  readonly commissionPct: string;
  readonly commissionAmount: string;
  readonly todBase: string;
  readonly todPct: string;
  readonly todAmount: string;
  readonly total: string;
  readonly remark: string | null;
  readonly recordedBy: NameRef;
  readonly recordedAt: string;
  readonly decidedBy: NameRef | null;
  readonly decidedAt: string | null;
  readonly decisionRemark: string | null;
  readonly paidOn: string | null;
  readonly paymentReference: string | null;
}

function toCommission(wire: z.output<typeof commissionWireSchema>): Commission {
  return {
    id: wire.id,
    application: {
      id: wire.application.id,
      number: wire.application.application_no,
      regNo: wire.application.reg_no,
    },
    partner: wire.partner,
    status: wire.status,
    costExclGst: wire.cost_excl_gst,
    aPlusB: wire.a_plus_b,
    giFitting: wire.gi_fitting,
    pvcHdpeFitting: wire.pvc_hdpe_fitting,
    installation: wire.installation,
    commissionBase: wire.commission_base,
    commissionPct: wire.commission_pct,
    commissionAmount: wire.commission_amount,
    todBase: wire.tod_base,
    todPct: wire.tod_pct,
    todAmount: wire.tod_amount,
    total: wire.total,
    remark: wire.remark,
    recordedBy: wire.recorded_by,
    recordedAt: wire.recorded_at,
    decidedBy: wire.decided_by,
    decidedAt: wire.decided_at,
    decisionRemark: wire.decision_remark,
    paidOn: wire.paid_on,
    paymentReference: wire.payment_reference,
  };
}

/** `{ data: Commission }`: the live one, a record, and every decision. */
export const commissionResponseSchema = z
  .object({ data: commissionWireSchema })
  .transform(({ data }) => toCommission(data));

export const commissionPageSchema = z
  .object({ data: z.array(commissionWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({ items: data.map(toCommission), nextCursor: meta.nextCursor }));
export type CommissionPage = z.output<typeof commissionPageSchema>;

const previewWireSchema = z.object({
  partner: nameRef,
  /** Includes installation, insurance, inspection, education and the sump. */
  cost_excl_gst: decimal,
  /** Material only (head and field units). */
  a_plus_b: decimal.nullable(),
  installation: decimal,
  /** Null when no rate is in force on the full-FP date: an admin adds one. */
  commission_pct: decimal.nullable(),
  tod_pct: decimal.nullable(),
  rate_id: z.string().nullable(),
});
export type CommissionPreviewWire = z.input<typeof previewWireSchema>;

/** SUBS-016 · Stage 18 before anything is typed: the stored calculation and the rate in force. */
export const commissionPreviewSchema = z
  .object({ data: previewWireSchema })
  .transform(({ data }) => ({
    partner: data.partner,
    costExclGst: data.cost_excl_gst,
    aPlusB: data.a_plus_b,
    installation: data.installation,
    commissionPct: data.commission_pct,
    todPct: data.tod_pct,
    rateId: data.rate_id,
  }));
export type CommissionPreview = z.output<typeof commissionPreviewSchema>;

/** POST /subsidy-applications/{id}/commission. A null installation or TOD base takes the default. */
export interface RecordCommissionRequest {
  readonly gi_fitting: string;
  readonly pvc_hdpe_fitting: string;
  readonly installation: string | null;
  readonly tod_base: string | null;
  readonly remark: string | null;
}

export interface CommissionListParams {
  /** Null lists every status. */
  readonly status: CommissionStatus | null;
}

/** approve, return and cancel. A remark is required to return or cancel. */
export interface DecisionRequest {
  readonly remark: string | null;
}

export interface PaymentRequest {
  readonly paid_on: string;
  readonly payment_reference: string;
}

// ── rates (SUBS-018) ─────────────────────────────────────────────────────────────

const rateWireSchema = z.object({
  id,
  scheme: z.string(),
  system_type: z.string().nullable(),
  partner_type: z.string().nullable(),
  partner: nameRef.nullable(),
  commission_pct: decimal,
  tod_pct: decimal,
  effective_from: isoDate,
});
export type RateWire = z.input<typeof rateWireSchema>;

export interface CommissionRate {
  readonly id: string;
  readonly scheme: string;
  readonly systemType: string | null;
  readonly partnerType: string | null;
  readonly partner: NameRef | null;
  readonly commissionPct: string;
  readonly todPct: string;
  readonly effectiveFrom: string;
}

function toRate(wire: z.output<typeof rateWireSchema>): CommissionRate {
  return {
    id: wire.id,
    scheme: wire.scheme,
    systemType: wire.system_type,
    partnerType: wire.partner_type,
    partner: wire.partner,
    commissionPct: wire.commission_pct,
    todPct: wire.tod_pct,
    effectiveFrom: wire.effective_from,
  };
}

export const rateListSchema = z
  .object({ data: z.array(rateWireSchema) })
  .transform(({ data }) => data.map(toRate));

export const rateResponseSchema = z
  .object({ data: rateWireSchema })
  .transform(({ data }) => toRate(data));

export interface AddRateRequest {
  readonly scheme: string;
  readonly system_type: RateSystemType | null;
  readonly partner_type: RatePartnerType | null;
  readonly partner_id: string | null;
  readonly commission_pct: string;
  readonly tod_pct: string;
  readonly effective_from: string;
}
