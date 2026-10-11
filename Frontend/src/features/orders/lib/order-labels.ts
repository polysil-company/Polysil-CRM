import type { BadgeVariant } from "@/components/ui/badge";
import type {
  OrderPdfState,
  OrderStatus,
  OrderType,
  PaymentTerms,
} from "@/features/orders/api/orders.schemas";
import { roleLabel } from "@/features/quotations/lib/quotation-lifecycle";

export const ORDER_STATUS_LABELS: Readonly<Record<OrderStatus, string>> = {
  draft: "Draft",
  submitted: "Waiting for approval",
  approved: "Approved",
  partially_dispatched: "Partly dispatched",
  dispatched: "Dispatched",
  closed_short: "Closed short",
  cancelled: "Cancelled",
};

/** The label always travels with the colour, so colour is never the only signal. */
export const ORDER_STATUS_BADGE: Readonly<Record<OrderStatus, BadgeVariant>> = {
  draft: "neutral",
  submitted: "warning",
  approved: "info",
  partially_dispatched: "primary",
  dispatched: "success",
  closed_short: "outline",
  cancelled: "danger",
};

export const ORDER_TYPE_LABELS: Readonly<Record<OrderType, string>> = {
  commercial: "Commercial",
  industrial: "Industrial",
  export: "Export",
  sample: "Sample",
  marketing_material: "Marketing material",
  subsidised: "Subsidised",
  replacement: "Replacement",
};

export const PAYMENT_TERMS_LABELS: Readonly<Record<PaymentTerms, string>> = {
  full_payment: "Full payment",
  credit: "Credit",
};

export const ORDER_PDF_LABELS: Readonly<Record<OrderPdfState, string>> = {
  none: "No PDF until approved",
  pending: "Preparing the PDF…",
  ready: "PDF ready",
  failed: "The PDF couldn't be made",
};

/** "SO/GJ/2026-27/00041", or "Draft order" — a draft has no number until it is submitted. */
export function orderNumber(order: { orderNo: string | null }): string {
  return order.orderNo ?? "Draft order";
}

/** "Waiting on State Manager", for the list and the approval card. */
export function waitingOnLabel(role: string | null): string | null {
  return role === null ? null : `Waiting on ${stepRoleLabel(role)}`;
}

/** Accounts and Dispatch are named by their desks, as the business says them. */
export function stepRoleLabel(role: string): string {
  switch (role) {
    case "account_manager":
      return "Accounts";
    case "dispatch_manager":
      return "Dispatch";
    default:
      return roleLabel(role);
  }
}

/** Warnings a dispatch is recorded with anyway. */
export const DISPATCH_WARNING_LABELS: Readonly<Record<string, string>> = {
  invoice_before_dc: "The invoice is dated before the delivery challan.",
  duplicate_invoice_no: "This invoice number is already on another dispatch.",
};

/** A quantity at three places, shown in the line's unit precision: "12.000" → "12", "2.500" → "2.5". */
export function formatOrderQty(qty: string, decimals: number): string {
  const value = Number(qty);
  if (!Number.isFinite(value)) {
    return qty;
  }
  const fixed = value.toFixed(Math.max(0, Math.min(3, decimals)));
  return fixed.includes(".") ? fixed.replace(/\.?0+$/, "") : fixed;
}
