import type { BadgeVariant } from "@/components/ui/badge";
import type {
  CommissionStatus,
  RatePartnerType,
  RateSystemType,
} from "@/features/commission/api/commission.schemas";

export const COMMISSION_STATUS_LABELS: Readonly<Record<CommissionStatus, string>> = {
  calculated: "To approve",
  approved: "To pay",
  returned: "Returned",
  paid: "Paid",
  cancelled: "Cancelled",
};

export const COMMISSION_STATUS_BADGE: Readonly<Record<CommissionStatus, BadgeVariant>> = {
  calculated: "warning",
  approved: "info",
  returned: "danger",
  paid: "success",
  cancelled: "neutral",
};

export const RATE_SYSTEM_LABELS: Readonly<Record<RateSystemType, string>> = {
  drip: "Drip",
  mini_sprinkler: "Mini sprinkler",
  sprinkler: "Sprinkler",
};

export const RATE_PARTNER_TYPE_LABELS: Readonly<Record<RatePartnerType, string>> = {
  distributor: "Distributors",
  dealer: "Dealers",
  sub_dealer: "Sub-dealers",
};

/** A stored code in words, or the code itself if it is new to the screen. */
export function labelFrom<TCode extends string>(
  labels: Readonly<Record<TCode, string>>,
  code: string | null,
  fallback: string,
): string {
  if (code === null) return fallback;
  const known = Object.entries<string>(labels).find(([key]) => key === code);
  return known?.[1] ?? code;
}

/** "5%", "2.5%": a percentage as typed, without trailing zeros. */
export function formatPct(value: string): string {
  return `${String(Number(value))}%`;
}

function paise(value: number): number {
  return Math.round((value + Number.EPSILON) * 100);
}

export interface CommissionInputs {
  readonly costExclGst: string;
  readonly giFitting: number;
  readonly pvcHdpeFitting: number;
  readonly installation: number;
  /** Null: the same as the commission base. */
  readonly todBase: number | null;
  readonly commissionPct: string;
  readonly todPct: string;
}

export interface CommissionFiguresInPaise {
  readonly base: number;
  readonly commission: number;
  readonly todBase: number;
  readonly tod: number;
  readonly total: number;
}

/**
 * What the server will store, as migration 037 checks it: the base is the cost before GST less
 * both fittings and the installation; each amount is its base times its rate, to the paisa; the
 * total is the two together. Shown while typing; the server's own figures are what is kept.
 */
export function workOutCommission(inputs: CommissionInputs): CommissionFiguresInPaise {
  const base = paise(
    Number(inputs.costExclGst) - inputs.giFitting - inputs.pvcHdpeFitting - inputs.installation,
  );
  const todBase = inputs.todBase === null ? base : paise(inputs.todBase);
  const commission = Math.round((base * Number(inputs.commissionPct)) / 100);
  const tod = Math.round((todBase * Number(inputs.todPct)) / 100);
  return { base, commission, todBase, tod, total: commission + tod };
}

/** Paise back to the decimal string the money formatter takes. */
export function rupees(paiseValue: number): string {
  return (paiseValue / 100).toFixed(2);
}
