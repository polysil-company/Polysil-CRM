import type { BadgeVariant } from "@/components/ui/badge";
import type {
  DuplicateSignal,
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
