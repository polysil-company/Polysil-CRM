import type { BadgeVariant } from "@/components/ui/badge";
import type { OrderPaymentStatus, PaymentMode } from "@/features/payments/api/payments.schemas";

export const PAYMENT_MODE_LABELS: Readonly<Record<PaymentMode, string>> = {
  neft: "NEFT / RTGS",
  upi: "UPI",
  cheque: "Cheque",
  cash: "Cash",
  adjustment: "Adjustment",
};

export const ORDER_PAYMENT_STATUS_LABELS: Readonly<Record<OrderPaymentStatus, string>> = {
  not_applicable: "Nothing to pay",
  unpaid: "Unpaid",
  part_paid: "Part paid",
  paid: "Paid",
  overpaid: "Overpaid",
};

export const ORDER_PAYMENT_STATUS_BADGE: Readonly<Record<OrderPaymentStatus, BadgeVariant>> = {
  not_applicable: "neutral",
  unpaid: "warning",
  part_paid: "info",
  paid: "success",
  overpaid: "highlight",
};

/** Rupees as typed: whole or with paise. */
export function rupeesProblem(value: string, required: boolean): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return required ? "Enter rupees." : null;
  return /^\d+(\.\d{1,2})?$/.test(trimmed) ? null : "Rupees, like 50000 or 50000.50.";
}

/** Rupees to paise, for sums that must not drift. */
export function toPaise(value: string): number {
  const parsed = Number(value.trim() === "" ? "0" : value);
  return Number.isFinite(parsed) ? Math.round(parsed * 100) : 0;
}

export function fromPaise(paise: number): string {
  return (paise / 100).toFixed(2);
}
