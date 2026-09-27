import type { BadgeVariant } from "@/components/ui/badge";
import type {
  PdfState,
  QuotationStatus,
  SalesType,
} from "@/features/quotations/api/quotations.schemas";
import { EMPTY_VALUE, formatNumber } from "@/lib/format";

export const QUOTATION_STATUS_LABELS: Readonly<Record<QuotationStatus, string>> = {
  draft: "Draft",
  sent: "Sent",
  viewed: "Viewed",
  negotiation: "Negotiation",
  accepted: "Accepted",
  rejected: "Rejected",
  expired: "Expired",
};

/** The label always travels with the colour, so colour is never the only signal. */
export const QUOTATION_STATUS_BADGE: Readonly<Record<QuotationStatus, BadgeVariant>> = {
  draft: "neutral",
  sent: "info",
  viewed: "primary",
  negotiation: "warning",
  accepted: "success",
  rejected: "danger",
  expired: "outline",
};

export const SALES_TYPE_LABELS: Readonly<Record<SalesType, string>> = {
  commercial: "Commercial",
  industrial: "Industrial",
  export: "Export",
  subsidised: "Subsidised",
  marketing: "Marketing",
  sample: "Sample",
};

export const PDF_STATE_LABELS: Readonly<Record<PdfState, string>> = {
  pending: "Preparing the PDF…",
  ready: "PDF ready",
  failed: "The PDF couldn't be made",
};

/** "QT/GJ/2026-27/00001", or "Draft" — a draft has no number until it is sent. */
export function quotationNumber(quotation: { quoteNo: string | null }): string {
  return quotation.quoteNo ?? "Draft";
}

/** "QT/GJ/2026-27/00001 · v2": the version shows only once there is more than one. */
export function quotationTitle(quotation: { quoteNo: string | null; version: number }): string {
  const number = quotationNumber(quotation);
  return quotation.version > 1 ? `${number} · v${String(quotation.version)}` : number;
}

/** "2.50" → "2.5", "18" → "18": trailing zeros go only after a decimal point. */
function trimFraction(text: string): string {
  return text.includes(".") ? text.replace(/\.?0+$/, "") : text;
}

/**
 * "10.000" → "10%", "2.500" → "2.5%", "0.000" → "0%". Rates arrive as decimal strings at three
 * places; this is for display only, never for arithmetic.
 */
export function formatRate(rate: string): string {
  const value = Number(rate);
  if (!Number.isFinite(value)) {
    return EMPTY_VALUE;
  }
  return `${trimFraction(formatNumber(value, Number.isInteger(value) ? 0 : 2))}%`;
}

/** "18.000" → "18", "2.500" → "2.5": a quantity without trailing zeros. */
export function formatQuantity(qty: string): string {
  const value = Number(qty);
  return Number.isFinite(value)
    ? trimFraction(formatNumber(value, Number.isInteger(value) ? 0 : 3))
    : EMPTY_VALUE;
}

export interface QuotationWarning {
  readonly code: string;
  readonly message: string;
}

/**
 * Each warning is "code: sentence". Split on the first colon: the code decides nothing on
 * screen yet, the sentence is shown. A warning without a code is shown whole.
 */
export function parseWarnings(warnings: readonly string[]): QuotationWarning[] {
  return warnings.map((warning) => {
    const colon = warning.indexOf(":");
    if (colon <= 0) {
      return { code: "", message: warning.trim() };
    }
    const message = warning.slice(colon + 1).trim();
    return {
      code: warning.slice(0, colon).trim(),
      message:
        message === "" ? warning.trim() : `${message.charAt(0).toUpperCase()}${message.slice(1)}`,
    };
  });
}
