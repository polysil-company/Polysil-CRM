import type { BadgeVariant } from "@/components/ui/badge";
import type { LeadSource, LeadStatus, OrderType } from "@/features/leads/api/leads.schemas";

export const LEAD_STATUS_LABELS: Readonly<Record<LeadStatus, string>> = {
  new: "New",
  contacted: "Contacted",
  qualified: "Qualified",
  quoted: "Quoted",
  negotiation: "Negotiation",
  won: "Won",
  lost: "Lost",
};

export const LEAD_STATUS_BADGE: Readonly<Record<LeadStatus, BadgeVariant>> = {
  new: "info",
  contacted: "neutral",
  qualified: "primary",
  quoted: "outline",
  negotiation: "warning",
  won: "success",
  lost: "danger",
};

export const LEAD_SOURCE_LABELS: Readonly<Record<LeadSource, string>> = {
  whatsapp: "WhatsApp",
  website: "Website",
  employee: "Field entry",
  qr_code: "QR code",
  phone_email: "Phone / email",
  offline: "Offline",
};

export const ORDER_TYPE_LABELS: Readonly<Record<OrderType, string>> = {
  subsidised: "Subsidised",
  commercial: "Commercial",
  industrial: "Industrial",
  export: "Export",
  complaint: "Complaint",
};
