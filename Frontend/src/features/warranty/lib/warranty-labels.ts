import type { BadgeVariant } from "@/components/ui/badge";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import type {
  ClaimWarrantyStatus,
  LineWarrantyStatus,
} from "@/features/warranty/api/warranty.schemas";

/** The order line's chip: "In warranty until 1 Oct 2027", "Expired 1 Oct 2027", … */
export function lineWarrantyText(status: LineWarrantyStatus, end: string | null): string {
  switch (status) {
    case "active":
      return end === null ? "In warranty" : `In warranty until ${formatBusinessDay(end)}`;
    case "expired":
      return end === null ? "Expired" : `Expired ${formatBusinessDay(end)}`;
    case "none":
      return "No warranty";
    case "unknown":
      return "No period on record";
    case "not_dispatched":
      return "Not sent yet";
  }
}

export const LINE_WARRANTY_BADGE: Readonly<Record<LineWarrantyStatus, BadgeVariant>> = {
  active: "success",
  expired: "neutral",
  none: "outline",
  unknown: "warning",
  not_dispatched: "outline",
};

export const CLAIM_WARRANTY_LABELS: Readonly<Record<ClaimWarrantyStatus, string>> = {
  in_warranty: "In warranty",
  expired: "Out of warranty",
  none: "No warranty",
  unknown: "No period on record",
};

export const CLAIM_WARRANTY_BADGE: Readonly<Record<ClaimWarrantyStatus, BadgeVariant>> = {
  in_warranty: "success",
  expired: "warning",
  none: "outline",
  unknown: "neutral",
};

/** "12 months", "No warranty" for 0. */
export function monthsText(months: number): string {
  if (months === 0) return "No warranty";
  return `${String(months)} ${months === 1 ? "month" : "months"}`;
}
