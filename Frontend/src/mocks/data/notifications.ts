import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type { NotificationWire } from "@/features/notifications/api/notifications.schemas";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";

import { mockLeadLabel } from "./messages";

function minutesAgo(now: number, minutes: number): string {
  return new Date(now - minutes * 60_000).toISOString();
}

function leadResource(lead: LeadWire | undefined): NotificationWire["resource"] {
  return lead ? { type: "lead", id: lead.id, label: mockLeadLabel(lead) } : null;
}

/** "QT/GJ/2026-27/00003" or "Draft", as the backend labels a record for its link text. */
function documentLabel(number: string | null | undefined): string {
  return number ?? "Draft";
}

/**
 * Seeded notifications for the signed-in staff user: approvals waiting on them, and
 * leads and tasks assigned to them. Three unread, three read. The quotation and order they
 * point at are seeded too, so their links open real pages.
 */
export function generateNotifications(
  leads: readonly LeadWire[],
  documents: {
    readonly quotation?: QuotationWire | undefined;
    readonly order?: OrderWire | undefined;
  } = {},
  now: number = Date.now(),
): NotificationWire[] {
  const [firstLead, secondLead, thirdLead] = leads;
  const { quotation, order } = documents;
  const quoteLabel = documentLabel(quotation?.quote_no);
  const orderLabel = documentLabel(order?.order_no);

  return [
    {
      id: "ntf-006",
      kind: "approval_requested",
      title: `A discount for ${quotation?.party.name ?? "Patel Farms"} needs your approval`,
      body: "Raised by Priya Nair: a repeat customer, matching a competitor's offer.",
      actor: { id: "usr-002", full_name: "Priya Nair" },
      resource: { type: "quotation", id: quotation?.id ?? "quo-00412", label: quoteLabel },
      created_at: minutesAgo(now, 12),
      read_at: null,
    },
    {
      id: "ntf-005",
      kind: "lead_assigned",
      title: "Rohan Mehta assigned you a lead",
      body: firstLead ? `${firstLead.farmer_name}, ${firstLead.territory.name}` : null,
      actor: { id: "usr-003", full_name: "Rohan Mehta" },
      resource: leadResource(firstLead),
      created_at: minutesAgo(now, 45),
      read_at: null,
    },
    {
      id: "ntf-004",
      kind: "task_assigned",
      title: "Follow-up call due today",
      body: secondLead ? `Call ${secondLead.farmer_name} about the drip layout quote.` : null,
      actor: { id: "usr-004", full_name: "Kavita Joshi" },
      resource: { type: "task", id: "tsk-2201", label: "Follow-up call" },
      created_at: minutesAgo(now, 130),
      read_at: null,
    },
    {
      id: "ntf-003",
      kind: "order_approved",
      title: `Sales order ${orderLabel} was approved`,
      body: `For ${order?.party.name ?? "Shah Agro Traders"}. The PDF is ready to share.`,
      actor: { id: "usr-009", full_name: "Deepak Solanki" },
      resource: { type: "sales_order", id: order?.id ?? "so-00188", label: orderLabel },
      created_at: minutesAgo(now, 300),
      read_at: minutesAgo(now, 280),
    },
    {
      id: "ntf-002",
      kind: "lead_assigned",
      title: "Priya Nair assigned you a lead",
      body: thirdLead ? `${thirdLead.farmer_name}, ${thirdLead.territory.name}` : null,
      actor: { id: "usr-002", full_name: "Priya Nair" },
      resource: leadResource(thirdLead),
      created_at: minutesAgo(now, 1500),
      read_at: minutesAgo(now, 1400),
    },
    {
      id: "ntf-001",
      kind: "task_assigned",
      title: "Site visit scheduled",
      body: "Karjan cluster demo plot, Friday 10:00 am.",
      actor: { id: "usr-008", full_name: "Anjali Verma" },
      resource: { type: "task", id: "tsk-2188", label: "Site visit" },
      created_at: minutesAgo(now, 4300),
      read_at: minutesAgo(now, 4200),
    },
  ];
}
