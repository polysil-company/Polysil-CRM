import type { BadgeVariant } from "@/components/ui/badge";
import type {
  DuplicateSignal,
  Lead,
  LeadInquiryType,
  LeadPriority,
  LeadStage,
} from "@/features/leads/api/leads.schemas";

export const LEAD_STAGE_LABELS: Readonly<Record<LeadStage, string>> = {
  new: "New",
  contacted: "Contacted",
  qualified: "Qualified",
  quoted: "Quoted",
  negotiation: "Negotiation",
  won: "Won",
  lost: "Lost",
  merged: "Merged",
  dormant: "Dormant",
};

/** The label always travels with the colour, so colour is never the only signal. */
export const LEAD_STAGE_BADGE: Readonly<Record<LeadStage, BadgeVariant>> = {
  new: "info",
  contacted: "neutral",
  qualified: "primary",
  quoted: "outline",
  negotiation: "warning",
  won: "success",
  lost: "danger",
  merged: "outline",
  dormant: "neutral",
};

export const LEAD_INQUIRY_TYPE_LABELS: Readonly<Record<LeadInquiryType, string>> = {
  commercial: "Commercial",
  subsidised: "Subsidised",
  industrial: "Industrial",
};

export const LEAD_PRIORITY_LABELS: Readonly<Record<LeadPriority, string>> = {
  hot: "Hot",
  warm: "Warm",
  cold: "Cold",
};

export const LEAD_PRIORITY_BADGE: Readonly<Record<LeadPriority, BadgeVariant>> = {
  hot: "danger",
  warm: "warning",
  cold: "info",
};

/** How two leads matched, in words a salesperson uses. */
export const DUPLICATE_SIGNAL_LABELS: Readonly<Record<DuplicateSignal, string>> = {
  mobile: "same mobile number",
  email: "same email",
  name_geo: "same name and place",
};

const PARTNER_TYPE_LABELS: Readonly<Record<string, string>> = {
  distributor: "Distributor",
  dealer: "Dealer",
  sub_dealer: "Sub-dealer",
};

/** "sub_dealer" → "Sub-dealer"; an unknown type is shown as sent. */
export function partnerTypeLabel(partnerType: string): string {
  return PARTNER_TYPE_LABELS[partnerType] ?? partnerType;
}

/**
 * "Ramesh Patel · POL/GJ/2026-27/00123", plus every possible duplicate the backend flagged,
 * so the toast counts the same as the lead page.
 */
export function describeCreatedLead(
  lead: Pick<Lead, "customerName" | "code" | "duplicates">,
): string {
  const created = `${lead.customerName} · ${lead.code}`;
  const pending = lead.duplicates.filter((candidate) => candidate.state === "pending");
  const [first] = pending;
  if (first === undefined) {
    return created;
  }
  if (pending.length === 1) {
    return `${created}. Possible duplicate of ${first.code} (${DUPLICATE_SIGNAL_LABELS[first.signal]}), flagged for review.`;
  }
  const codes = pending.map((candidate) => candidate.code);
  const listed = `${codes.slice(0, -1).join(", ")} and ${codes.at(-1) ?? ""}`;
  return `${created}. ${String(pending.length)} possible duplicates (${listed}), flagged for review.`;
}

/** "4.50" → "4.5", "12.00" → "12": land in acres as people say it. */
export function formatAcres(acres: string): string {
  const value = Number(acres);
  if (!Number.isFinite(value)) {
    return acres;
  }
  return value.toFixed(2).replace(/\.?0+$/, "");
}
