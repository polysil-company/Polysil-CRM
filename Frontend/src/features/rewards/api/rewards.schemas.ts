import { z } from "zod";

import { pageMetaSchema } from "@/lib/api/pagination";

/**
 * RWD-001 … RWD-003 · Reward points (FS-032; `backend/docs/handover/rewards-contract.md`,
 * `docs/api/rewards.md`). Dealers and staff earn points by rules the admin sets; dealers spend
 * them on a gift (or on an order). Points are whole numbers; money is a decimal string.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.iso.date();
const isoDateTime = z.iso.datetime({ offset: true });

export const LEDGER_KINDS = [
  "earned",
  "reversed",
  "redeemed",
  "released",
  "expired",
  "adjusted",
] as const;
export type LedgerKind = (typeof LEDGER_KINDS)[number];

export const REDEMPTION_STATUSES = [
  "pending",
  "applied",
  "fulfilled",
  "rejected",
  "withdrawn",
  "released",
] as const;
export type RedemptionStatus = (typeof REDEMPTION_STATUSES)[number];

export const RULE_HOLDERS = ["partner", "staff"] as const;
export type RuleHolder = (typeof RULE_HOLDERS)[number];

export const RULE_BASES = ["order_value", "lead_won"] as const;
export type RuleBasis = (typeof RULE_BASES)[number];

const holderSchema = z.object({
  type: z.enum(["partner", "user"]),
  id,
  name: z.string().nullable(),
});
export type Holder = z.output<typeof holderSchema>;

// ── balance and history ──────────────────────────────────────────────────────────

const balanceWireSchema = z.object({
  holder: holderSchema,
  /** May be below zero after a reversal. */
  balance: z.number().int(),
  point_value: decimal,
});

export interface Balance {
  readonly holder: Holder;
  readonly points: number;
  /** Rupees one point is worth on an order today. */
  readonly pointValue: string;
}

export const balanceResponseSchema = z
  .object({ data: balanceWireSchema })
  .transform(({ data }): Balance => ({
    holder: data.holder,
    points: data.balance,
    pointValue: data.point_value,
  }));

const ledgerRowWireSchema = z.object({
  id,
  points: z.number().int(),
  kind: z.enum(LEDGER_KINDS),
  reason: z.string(),
  at: isoDateTime,
  expires_at: isoDateTime.nullable(),
});
export type LedgerRowWire = z.input<typeof ledgerRowWireSchema>;

export interface LedgerRow {
  readonly id: string;
  readonly points: number;
  readonly kind: LedgerKind;
  readonly reason: string;
  readonly at: string;
  readonly expiresAt: string | null;
}

function toLedgerRow(wire: z.output<typeof ledgerRowWireSchema>): LedgerRow {
  return {
    id: wire.id,
    points: wire.points,
    kind: wire.kind,
    reason: wire.reason,
    at: wire.at,
    expiresAt: wire.expires_at,
  };
}

export const ledgerPageSchema = z
  .object({ data: z.array(ledgerRowWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({ items: data.map(toLedgerRow), nextCursor: meta.nextCursor }));
export type LedgerPage = z.output<typeof ledgerPageSchema>;

export const ledgerRowResponseSchema = z
  .object({ data: ledgerRowWireSchema })
  .transform(({ data }) => toLedgerRow(data));

/** Whose points: your own (null), a partner's or a user's in your scope. */
export type HolderQuery =
  | { readonly kind: "me" }
  | { readonly kind: "partner"; readonly id: string }
  | { readonly kind: "user"; readonly id: string };

// ── gifts ────────────────────────────────────────────────────────────────────────

const giftWireSchema = z.object({
  id,
  name: z.string(),
  description: z.string().nullable(),
  points_cost: z.number().int(),
  is_active: z.boolean(),
});
export type GiftWire = z.input<typeof giftWireSchema>;

export interface Gift {
  readonly id: string;
  readonly name: string;
  readonly description: string | null;
  readonly pointsCost: number;
  readonly active: boolean;
}

function toGift(wire: z.output<typeof giftWireSchema>): Gift {
  return {
    id: wire.id,
    name: wire.name,
    description: wire.description,
    pointsCost: wire.points_cost,
    active: wire.is_active,
  };
}

export const giftListSchema = z
  .object({ data: z.array(giftWireSchema) })
  .transform(({ data }) => data.map(toGift));
export const giftResponseSchema = z
  .object({ data: giftWireSchema })
  .transform(({ data }) => toGift(data));

export interface GiftCreateRequest {
  readonly name: string;
  readonly description: string | null;
  readonly points_cost: number;
}

export interface GiftPatchRequest {
  readonly name?: string;
  readonly description?: string | null;
  readonly points_cost?: number;
  readonly is_active?: boolean;
}

// ── redemptions ──────────────────────────────────────────────────────────────────

const redemptionWireSchema = z.object({
  id,
  kind: z.enum(["order", "gift"]),
  holder: holderSchema,
  points: z.number().int(),
  /** An order redemption once submitted: the rupees taken off the payable. */
  amount: decimal.nullable(),
  status: z.enum(REDEMPTION_STATUSES),
  gift: giftWireSchema.nullable(),
  sales_order: z.object({ id, order_no: z.string().nullable() }).nullable(),
  remark: z.string().nullable(),
  decided_at: isoDateTime.nullable(),
  created_at: isoDateTime,
});
export type RedemptionWire = z.input<typeof redemptionWireSchema>;

export interface Redemption {
  readonly id: string;
  readonly kind: "order" | "gift";
  readonly holder: Holder;
  readonly points: number;
  readonly amount: string | null;
  readonly status: RedemptionStatus;
  readonly gift: Gift | null;
  readonly salesOrder: { readonly id: string; readonly orderNo: string | null } | null;
  readonly remark: string | null;
  readonly decidedAt: string | null;
  readonly createdAt: string;
}

function toRedemption(wire: z.output<typeof redemptionWireSchema>): Redemption {
  return {
    id: wire.id,
    kind: wire.kind,
    holder: wire.holder,
    points: wire.points,
    amount: wire.amount,
    status: wire.status,
    gift: wire.gift === null ? null : toGift(wire.gift),
    salesOrder:
      wire.sales_order === null
        ? null
        : { id: wire.sales_order.id, orderNo: wire.sales_order.order_no },
    remark: wire.remark,
    decidedAt: wire.decided_at,
    createdAt: wire.created_at,
  };
}

export const redemptionPageSchema = z
  .object({ data: z.array(redemptionWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({ items: data.map(toRedemption), nextCursor: meta.nextCursor }));
export type RedemptionPage = z.output<typeof redemptionPageSchema>;

export const redemptionResponseSchema = z
  .object({ data: redemptionWireSchema })
  .transform(({ data }) => toRedemption(data));

export interface RedemptionListParams {
  readonly status: RedemptionStatus | null;
  readonly kind: "order" | "gift" | null;
}

// ── rules and settings ───────────────────────────────────────────────────────────

const ruleWireSchema = z.object({
  id,
  code: z.string(),
  name: z.string(),
  holder: z.enum(RULE_HOLDERS),
  basis: z.enum(RULE_BASES),
  points: z.number().int(),
  per_amount: decimal.nullable(),
  valid_from: isoDate,
  valid_to: isoDate.nullable(),
  expiry_days: z.number().int().nullable(),
  is_active: z.boolean(),
  /** It has awarded points: only the end date and the active flag can change. */
  used: z.boolean(),
});
export type RuleWire = z.input<typeof ruleWireSchema>;

export interface RewardRule {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly holder: RuleHolder;
  readonly basis: RuleBasis;
  readonly points: number;
  readonly perAmount: string | null;
  readonly validFrom: string;
  readonly validTo: string | null;
  readonly expiryDays: number | null;
  readonly active: boolean;
  readonly used: boolean;
}

function toRule(wire: z.output<typeof ruleWireSchema>): RewardRule {
  return {
    id: wire.id,
    code: wire.code,
    name: wire.name,
    holder: wire.holder,
    basis: wire.basis,
    points: wire.points,
    perAmount: wire.per_amount,
    validFrom: wire.valid_from,
    validTo: wire.valid_to,
    expiryDays: wire.expiry_days,
    active: wire.is_active,
    used: wire.used,
  };
}

export const ruleListSchema = z
  .object({ data: z.array(ruleWireSchema) })
  .transform(({ data }) => data.map(toRule));
export const ruleResponseSchema = z
  .object({ data: ruleWireSchema })
  .transform(({ data }) => toRule(data));

export interface RuleCreateRequest {
  readonly code: string;
  readonly name: string;
  readonly holder: RuleHolder;
  readonly basis: RuleBasis;
  readonly points: number;
  readonly per_amount: string | null;
  readonly valid_from: string;
  readonly valid_to: string | null;
  readonly expiry_days: number | null;
}

export interface RulePatchRequest {
  readonly name?: string;
  readonly points?: number;
  readonly per_amount?: string | null;
  readonly valid_from?: string;
  readonly valid_to?: string | null;
  readonly expiry_days?: number | null;
  readonly is_active?: boolean;
}

const settingsWireSchema = z.object({
  point_value: decimal,
  max_redeem_pct: decimal,
  effective_from: isoDate,
});
export type RewardSettingsWire = z.input<typeof settingsWireSchema>;

export interface RewardSettings {
  readonly pointValue: string;
  /** The most of an order's total, GST included, points may pay. */
  readonly maxRedeemPct: string;
  readonly effectiveFrom: string;
}

export const settingsResponseSchema = z
  .object({ data: settingsWireSchema })
  .transform(({ data }): RewardSettings => ({
    pointValue: data.point_value,
    maxRedeemPct: data.max_redeem_pct,
    effectiveFrom: data.effective_from,
  }));

export interface SettingsRequest {
  readonly point_value: string;
  readonly max_redeem_pct: string;
}

/** DELETE answers 204 with no body. */
export const noContentSchema = z.undefined();

export interface AdjustmentRequest {
  readonly partner_id: string | null;
  readonly user_id: string | null;
  /** Positive adds, negative takes away; never zero. */
  readonly points: number;
  readonly reason: string;
}
