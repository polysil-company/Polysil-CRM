import type { Lead } from "@/features/leads/api/leads.schemas";
import type { NotificationWire } from "@/features/notifications/api/notifications.schemas";

import { mockLeadLabel } from "./messages";

function minutesAgo(now: number, minutes: number): string {
  return new Date(now - minutes * 60_000).toISOString();
}

function leadResource(lead: Lead | undefined): NotificationWire["resource"] {
  return lead ? { type: "lead", id: lead.id, label: mockLeadLabel(lead) } : null;
}

/**
 * Seeded notifications for the signed-in staff user: approvals waiting on them, and
 * leads and tasks assigned to them. Three unread, three read.
 */
export function generateNotifications(
  leads: readonly Lead[],
  now: number = Date.now(),
): NotificationWire[] {
  const [firstLead, secondLead, thirdLead] = leads;

  return [
    {
      id: "ntf-006",
      kind: "approval_requested",
      title: "Quotation QT-26-00412 needs your approval",
      body: "₹4,80,000 for Patel Farms, raised by Priya Nair.",
      actor: { id: "usr-002", full_name: "Priya Nair" },
      resource: { type: "quotation", id: "quo-00412", label: "QT-26-00412" },
      created_at: minutesAgo(now, 12),
      read_at: null,
    },
    {
      id: "ntf-005",
      kind: "lead_assigned",
      title: "Rohan Mehta assigned you a lead",
      body: firstLead ? `${firstLead.customerName}, ${firstLead.district}` : null,
      actor: { id: "usr-003", full_name: "Rohan Mehta" },
      resource: leadResource(firstLead),
      created_at: minutesAgo(now, 45),
      read_at: null,
    },
    {
      id: "ntf-004",
      kind: "task_assigned",
      title: "Follow-up call due today",
      body: secondLead ? `Call ${secondLead.customerName} about the drip layout quote.` : null,
      actor: { id: "usr-004", full_name: "Kavita Joshi" },
      resource: { type: "task", id: "tsk-2201", label: "Follow-up call" },
      created_at: minutesAgo(now, 130),
      read_at: null,
    },
    {
      id: "ntf-003",
      kind: "approval_requested",
      title: "Sales order SO-26-00188 needs your approval",
      body: "₹2,15,000 for Shah Agro Traders, raised by Deepak Solanki.",
      actor: { id: "usr-009", full_name: "Deepak Solanki" },
      resource: { type: "sales_order", id: "so-00188", label: "SO-26-00188" },
      created_at: minutesAgo(now, 300),
      read_at: minutesAgo(now, 280),
    },
    {
      id: "ntf-002",
      kind: "lead_assigned",
      title: "Priya Nair assigned you a lead",
      body: thirdLead ? `${thirdLead.customerName}, ${thirdLead.district}` : null,
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
