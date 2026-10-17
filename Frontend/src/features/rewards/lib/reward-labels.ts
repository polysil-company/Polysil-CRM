import type { BadgeVariant } from "@/components/ui/badge";
import type {
  LedgerKind,
  RedemptionStatus,
  RewardRule,
  RuleBasis,
  RuleHolder,
} from "@/features/rewards/api/rewards.schemas";
import { formatInr, formatNumber } from "@/lib/format";

export const LEDGER_KIND_LABELS: Readonly<Record<LedgerKind, string>> = {
  earned: "Earned",
  reversed: "Taken back",
  redeemed: "Spent or held",
  released: "Given back",
  expired: "Expired",
  adjusted: "Adjusted",
};

export const REDEMPTION_STATUS_LABELS: Readonly<Record<RedemptionStatus, string>> = {
  pending: "Waiting",
  applied: "Used on the order",
  fulfilled: "Sent",
  rejected: "Refused",
  withdrawn: "Withdrawn",
  released: "Given back",
};

export const REDEMPTION_STATUS_BADGE: Readonly<Record<RedemptionStatus, BadgeVariant>> = {
  pending: "warning",
  applied: "success",
  fulfilled: "success",
  rejected: "danger",
  withdrawn: "neutral",
  released: "neutral",
};

export const RULE_HOLDER_LABELS: Readonly<Record<RuleHolder, string>> = {
  partner: "Channel partners",
  staff: "Staff",
};

export const RULE_BASIS_LABELS: Readonly<Record<RuleBasis, string>> = {
  order_value: "On a delivered order's value",
  lead_won: "On a lead won",
};

/** "1,240 points", "1 point". */
export function pointsText(points: number): string {
  return `${formatNumber(points)} ${Math.abs(points) === 1 ? "point" : "points"}`;
}

/** "+240", "−60": a ledger movement with its sign. */
export function signedPoints(points: number): string {
  return points > 0 ? `+${formatNumber(points)}` : `−${formatNumber(Math.abs(points))}`;
}

/** What a number of points is worth on an order at today's value. */
export function pointsWorth(points: number, pointValue: string): string {
  return formatInr((Math.max(0, points) * Number(pointValue)).toFixed(2), { paise: true });
}

/** A rule in words: "1 point for every ₹1,000 of a delivered order, for channel partners". */
export function ruleInWords(rule: RewardRule): string {
  const who = RULE_HOLDER_LABELS[rule.holder].toLowerCase();
  if (rule.basis === "lead_won") return `${pointsText(rule.points)} for each lead won, for ${who}`;
  const per = rule.perAmount === null ? "" : ` for every ${formatInr(rule.perAmount)}`;
  return `${pointsText(rule.points)}${per} of a delivered order, before GST, for ${who}`;
}
