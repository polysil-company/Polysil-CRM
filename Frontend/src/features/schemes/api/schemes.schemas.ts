import { z } from "zod";

import { pageMetaSchema } from "@/lib/api/pagination";

/**
 * SCHM-001 … SCHM-004 · Promotional schemes (`backend/docs/handover/schemes-contract.md`, read
 * against `api/schemas/schemes.py`). Admin defines them; dealers see the ones aimed at them, a
 * period scheme's standing, and their credits. Money and figures are decimal strings.
 */

const id = z.string().min(1);
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);
const isoDate = z.iso.date();
const isoDateTime = z.iso.datetime({ offset: true });

export const SCHEME_TYPES = ["order_discount", "order_points", "next_order", "period"] as const;
export type SchemeType = (typeof SCHEME_TYPES)[number];

export const BENEFIT_KINDS = ["pct", "flat", "points"] as const;
export type BenefitKind = (typeof BENEFIT_KINDS)[number];

/** Which benefits each type takes (backend `KINDS_FOR_TYPE`). */
export const KINDS_FOR_TYPE: Readonly<Record<SchemeType, readonly BenefitKind[]>> = {
  order_discount: ["pct", "flat"],
  order_points: ["points"],
  next_order: ["pct", "flat"],
  period: ["pct", "flat", "points"],
};

export const CONDITION_METRICS = ["order_value", "product_qty"] as const;
export type ConditionMetric = (typeof CONDITION_METRICS)[number];

export const SCHEME_PERIODS = ["month", "quarter"] as const;
export type SchemePeriod = (typeof SCHEME_PERIODS)[number];

export const TARGET_TYPES = [
  "territory",
  "partner_type",
  "partner",
  "product",
  "product_category",
] as const;
export type TargetType = (typeof TARGET_TYPES)[number];

export const PARTNER_TYPES = ["distributor", "dealer", "sub_dealer"] as const;

export const SCHEME_STATUSES = ["current", "active", "inactive"] as const;
export type SchemeStatus = (typeof SCHEME_STATUSES)[number];

export const ENTITLEMENT_STATUSES = ["available", "consumed", "expired", "reversed"] as const;
export type EntitlementStatus = (typeof ENTITLEMENT_STATUSES)[number];

/** A default the backend applies to a credit's life when none is given (GAP-307). */
export const DEFAULT_ENTITLEMENT_DAYS = 90;

const targetSchema = z.object({
  type: z.enum(TARGET_TYPES),
  id: z.string().min(1),
  /** BE-027 · The record's name (for a partner type, the type); null outside your scope. */
  name: z.string().nullish(),
});

export type SchemeTarget = z.output<typeof targetSchema>;

export const schemeWireSchema = z.object({
  id,
  code: z.string().min(1),
  name: z.string(),
  description: z.string().nullable(),
  scheme_type: z.enum(SCHEME_TYPES),
  condition: z.object({
    metric: z.enum(CONDITION_METRICS),
    min: decimal,
    max: decimal.nullable(),
  }),
  benefit: z.object({
    kind: z.enum(BENEFIT_KINDS),
    value: decimal,
    cap: decimal.nullable(),
    entitlement_days: z.number().int().nullable(),
  }),
  period: z.enum(SCHEME_PERIODS).nullable(),
  valid_from: isoDate,
  valid_to: isoDate.nullable(),
  priority: z.number().int(),
  stackable: z.boolean(),
  is_active: z.boolean(),
  /** Active, and today within its dates. */
  is_current: z.boolean(),
  /** It has given a benefit: only the end date and the active switch can change. */
  used: z.boolean(),
  /** A partner user never sees partner targets. */
  targets: z.array(targetSchema),
  created_at: isoDateTime,
});

export type SchemeWire = z.input<typeof schemeWireSchema>;

export interface Scheme {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string | null;
  readonly type: SchemeType;
  readonly condition: {
    readonly metric: ConditionMetric;
    readonly min: string;
    readonly max: string | null;
  };
  readonly benefit: {
    readonly kind: BenefitKind;
    readonly value: string;
    readonly cap: string | null;
    readonly entitlementDays: number | null;
  };
  readonly period: SchemePeriod | null;
  readonly validFrom: string;
  readonly validTo: string | null;
  readonly priority: number;
  readonly stackable: boolean;
  readonly isActive: boolean;
  readonly isCurrent: boolean;
  readonly used: boolean;
  readonly targets: readonly SchemeTarget[];
  readonly createdAt: string;
}

function toScheme(wire: z.output<typeof schemeWireSchema>): Scheme {
  return {
    id: wire.id,
    code: wire.code,
    name: wire.name,
    description: wire.description,
    type: wire.scheme_type,
    condition: wire.condition,
    benefit: {
      kind: wire.benefit.kind,
      value: wire.benefit.value,
      cap: wire.benefit.cap,
      entitlementDays: wire.benefit.entitlement_days,
    },
    period: wire.period,
    validFrom: wire.valid_from,
    validTo: wire.valid_to,
    priority: wire.priority,
    stackable: wire.stackable,
    isActive: wire.is_active,
    isCurrent: wire.is_current,
    used: wire.used,
    targets: wire.targets,
    createdAt: wire.created_at,
  };
}

export const schemeSchema = z
  .object({ data: schemeWireSchema })
  .transform(({ data }) => toScheme(data));

export const schemePageSchema = z
  .object({ data: z.array(schemeWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({ items: data.map(toScheme), nextCursor: meta.nextCursor }));

export type SchemePage = z.output<typeof schemePageSchema>;

export interface SchemeListParams {
  readonly status: SchemeStatus | null;
  readonly type: SchemeType | null;
  readonly q: string;
}

/** POST /schemes. */
export interface SchemeCreateRequest {
  readonly code: string;
  readonly name: string;
  readonly description: string | null;
  readonly scheme_type: SchemeType;
  readonly condition: { metric: ConditionMetric; min: string; max: string | null };
  readonly benefit: {
    kind: BenefitKind;
    value: string;
    cap: string | null;
    entitlement_days: number | null;
  };
  readonly period: SchemePeriod | null;
  readonly valid_from: string;
  readonly valid_to: string | null;
  readonly priority: number;
  readonly stackable: boolean;
  readonly targets: readonly { type: TargetType; id: string }[];
}

/** PATCH /schemes/{id}: any create field but the code, plus `is_active`. */
export type SchemePatchRequest = Partial<Omit<SchemeCreateRequest, "code">> & {
  readonly is_active?: boolean;
};

// ── standing (SCHM-003) ──────────────────────────────────────────────────────────

export const standingSchema = z
  .object({
    data: z.object({
      period_start: isoDate,
      period_end: isoDate,
      metric: z.enum(CONDITION_METRICS),
      achieved: decimal,
      min: decimal,
      max: decimal.nullable(),
      qualifies: z.boolean(),
    }),
  })
  .transform(({ data }) => ({
    periodStart: data.period_start,
    periodEnd: data.period_end,
    metric: data.metric,
    achieved: data.achieved,
    min: data.min,
    max: data.max,
    qualifies: data.qualifies,
  }));

export type Standing = z.output<typeof standingSchema>;
export type StandingWire = z.input<typeof standingSchema>["data"];

// ── credits (SCHM-004) ───────────────────────────────────────────────────────────

const schemeRefSchema = z.object({ id, code: z.string(), name: z.string() });
const orderRefSchema = z
  .object({ id, order_no: z.string().nullable() })
  .transform((wire) => ({ id: wire.id, orderNo: wire.order_no }));

export const entitlementWireSchema = z.object({
  id,
  scheme: schemeRefSchema,
  partner: z.object({ id, name: z.string() }),
  kind: z.enum(["pct", "flat"]),
  value: decimal,
  cap: decimal.nullable(),
  status: z.enum(ENTITLEMENT_STATUSES),
  earned_at: isoDateTime,
  expires_at: isoDateTime,
  source_order: orderRefSchema.nullable(),
  period_start: isoDate.nullable(),
  period_end: isoDate.nullable(),
  consumed_order: orderRefSchema.nullable(),
});

export type EntitlementWire = z.input<typeof entitlementWireSchema>;

export const entitlementPageSchema = z
  .object({ data: z.array(entitlementWireSchema), meta: pageMetaSchema })
  .transform(({ data, meta }) => ({
    items: data.map((wire) => ({
      id: wire.id,
      scheme: wire.scheme,
      partner: wire.partner,
      kind: wire.kind,
      value: wire.value,
      cap: wire.cap,
      status: wire.status,
      earnedAt: wire.earned_at,
      expiresAt: wire.expires_at,
      sourceOrder: wire.source_order,
      periodStart: wire.period_start,
      periodEnd: wire.period_end,
      consumedOrder: wire.consumed_order,
    })),
    nextCursor: meta.nextCursor,
  }));

export type EntitlementPage = z.output<typeof entitlementPageSchema>;
export type Entitlement = EntitlementPage["items"][number];

export interface EntitlementListParams {
  readonly status: EntitlementStatus | null;
  readonly partnerId: string | null;
}
