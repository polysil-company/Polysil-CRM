import type {
  ConditionMetric,
  EntitlementStatus,
  Scheme,
  SchemePeriod,
  SchemeType,
  TargetType,
} from "@/features/schemes/api/schemes.schemas";
import { formatFullDate, formatInr, formatNumber, todayInIndia } from "@/lib/format";

export const SCHEME_TYPE_LABELS: Readonly<Record<SchemeType, string>> = {
  order_discount: "Order discount",
  order_points: "Points on an order",
  next_order: "Credit for the next order",
  period: "Monthly or quarterly target",
};

/** What each type does, as the handover's table says it. */
export const SCHEME_TYPE_DESCRIPTIONS: Readonly<Record<SchemeType, string>> = {
  order_discount: "Taken off what the dealer owes when the order is submitted.",
  order_points: "Points to the dealer when the order is delivered.",
  next_order: "A credit earned on delivery and used on a later order.",
  period:
    "After each month or quarter, a credit or points if the dealer's delivered total met the target.",
};

export const PERIOD_LABELS: Readonly<Record<SchemePeriod, string>> = {
  month: "Month",
  quarter: "Quarter",
};

export const TARGET_TYPE_LABELS: Readonly<Record<TargetType, string>> = {
  territory: "Territory",
  partner_type: "Partner type",
  partner: "Partner",
  product: "Product",
  product_category: "Product category",
};

export const PARTNER_TYPE_LABELS: Readonly<Record<string, string>> = {
  distributor: "Distributors",
  dealer: "Dealers",
  sub_dealer: "Sub-dealers",
};

export const ENTITLEMENT_STATUS_LABELS: Readonly<Record<EntitlementStatus, string>> = {
  available: "Available",
  consumed: "Used",
  expired: "Expired",
  reversed: "Reversed",
};

/** An order value in rupees, or a quantity in units. */
export function formatFigure(metric: ConditionMetric, value: string): string {
  return metric === "order_value"
    ? formatInr(value)
    : `${formatNumber(Number(value), Number.isInteger(Number(value)) ? 0 : 3)} units`;
}

/** "Orders of ₹2,00,000 or more", "Any order", "Between 100 and 500 units". */
export function conditionText(scheme: Pick<Scheme, "type" | "condition" | "period">): string {
  const { metric, min, max } = scheme.condition;
  const counted = metric === "order_value" ? "order value" : "quantity";
  if (scheme.type === "period") {
    const span = scheme.period === "quarter" ? "quarter's" : "month's";
    return max === null
      ? `When the ${span} delivered ${counted} reaches ${formatFigure(metric, min)}`
      : `When the ${span} delivered ${counted} is between ${formatFigure(metric, min)} and ${formatFigure(metric, max)}`;
  }
  if (Number(min) === 0 && max === null) return "Any order";
  if (max === null) return `Orders of ${formatFigure(metric, min)} or more`;
  return `Orders between ${formatFigure(metric, min)} and ${formatFigure(metric, max)}`;
}

/** "5% off, up to ₹50,000", "A ₹3,000 credit for a later order, usable for 90 days", "200 points". */
export function benefitText(scheme: Pick<Scheme, "type" | "benefit">): string {
  const { kind, value, cap, entitlementDays } = scheme.benefit;
  const amount =
    kind === "pct"
      ? `${formatNumber(Number(value), Number.isInteger(Number(value)) ? 0 : 2)}%`
      : kind === "flat"
        ? formatInr(value)
        : `${formatNumber(Number(value))} points`;
  const upTo = cap === null ? "" : `, up to ${formatInr(cap)}`;
  if (kind === "points") return amount;
  if (scheme.type === "order_discount") return `${amount} off${upTo}`;
  const days = entitlementDays === null ? "" : `, usable for ${formatNumber(entitlementDays)} days`;
  return `A ${amount} credit for a later order${upTo}${days}`;
}

export type SchemeState = "running" | "scheduled" | "ended" | "off";

export const SCHEME_STATE_LABELS: Readonly<Record<SchemeState, string>> = {
  running: "Running",
  scheduled: "Scheduled",
  ended: "Ended",
  off: "Switched off",
};

export function schemeState(
  scheme: Pick<Scheme, "isActive" | "isCurrent" | "validFrom">,
  today: string = todayInIndia(),
): SchemeState {
  if (!scheme.isActive) return "off";
  if (scheme.isCurrent) return "running";
  return scheme.validFrom > today ? "scheduled" : "ended";
}

/** "5 Oct 2026 to 31 Dec 2026", or "From 5 Oct 2026, no end date". */
export function validityText(scheme: Pick<Scheme, "validFrom" | "validTo">): string {
  return scheme.validTo === null
    ? `From ${formatFullDate(scheme.validFrom)}, no end date`
    : `${formatFullDate(scheme.validFrom)} to ${formatFullDate(scheme.validTo)}`;
}
