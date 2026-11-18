import type { BadgeVariant } from "@/components/ui/badge";
import type {
  MarketingOrderStatus,
  Material,
  OrderView,
} from "@/features/marketing/api/marketing.schemas";

export const MARKETING_STATUS_LABELS: Readonly<Record<MarketingOrderStatus, string>> = {
  submitted: "Waiting for approval",
  approved: "Approved, to send",
  rejected: "Refused",
  cancelled: "Cancelled",
  dispatched: "Sent",
};

export const MARKETING_STATUS_BADGE: Readonly<Record<MarketingOrderStatus, BadgeVariant>> = {
  submitted: "warning",
  approved: "info",
  rejected: "danger",
  cancelled: "neutral",
  dispatched: "success",
};

export const ORDER_VIEW_LABELS: Readonly<Record<OrderView, string>> = {
  mine: "Mine",
  awaiting: "To approve",
  dispatch: "To send",
  all: "All",
};

/** Rupees to whole paise, so sums never drift. */
export function toPaise(value: string | null): number {
  const parsed = Number(value ?? "0");
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

export function fromPaise(paise: number): string {
  return (paise / 100).toFixed(2);
}

export interface SharePreview {
  readonly value: string;
  readonly companyShare: string;
  readonly dealerShare: string;
}

/**
 * The value and shares the order would carry, worked out as the backend does: price times
 * quantity, the company's share at the item's percentage, rounded to the paisa; an office's own
 * use is all the company's. The backend's figures on the saved order are the ones that count.
 */
export function previewShares(
  basket: Readonly<Record<string, number>>,
  materials: readonly Material[],
  officeUse: boolean,
): SharePreview {
  let value = 0;
  let company = 0;
  for (const material of materials) {
    const qty = basket[material.id] ?? 0;
    if (qty <= 0) continue;
    const lineValue = toPaise(material.price) * qty;
    const pct = officeUse ? 100 : Number(material.companySharePct ?? "0");
    value += lineValue;
    company += Math.round((lineValue * pct) / 100);
  }
  return {
    value: fromPaise(value),
    companyShare: fromPaise(company),
    dealerShare: fromPaise(value - company),
  };
}

/** "50%" from "50.00"; "33.5%" from "33.500". */
export function percentText(value: string | null): string {
  return value === null ? "—" : `${String(Number(value))}%`;
}
