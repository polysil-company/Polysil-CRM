import type { CustomerWire } from "@/features/customers/api/customers.schemas";
import type { LeadWire } from "@/features/leads/api/leads.schemas";

import { mockUuid } from "./reference";

/** The mock's own id space for customers. */
export const CUSTOMER_SPACE = 0xc057;

/** The stages at or past qualified: those leads have a customer (FS-041). */
const CUSTOMER_STAGES: readonly string[] = ["qualified", "quoted", "negotiation", "won"];

/**
 * LEAD-016 · One customer per mobile among the leads that reached qualified, as the backend's
 * deploy linked them; each such lead gets its `customer_id`. The first customer has consent.
 */
export function deriveCustomers(leads: LeadWire[]): CustomerWire[] {
  const byMobile = new Map<string, CustomerWire>();
  for (const lead of leads) {
    if (!CUSTOMER_STAGES.includes(lead.stage)) continue;
    let customer = byMobile.get(lead.mobile);
    if (customer === undefined) {
      customer = {
        id: mockUuid(CUSTOMER_SPACE, byMobile.size + 1),
        customer_type: "farmer",
        name: lead.farmer_name,
        mobile: lead.mobile,
        email: lead.email,
        territory: lead.territory,
        village: lead.village,
        address: null,
        survey_no: null,
        consent_given_at: byMobile.size === 0 ? lead.created_at : null,
        consent_channel: byMobile.size === 0 ? "whatsapp" : null,
        lead_count: 0,
        created_at: lead.created_at,
        updated_at: lead.created_at,
      };
      byMobile.set(lead.mobile, customer);
    }
    lead.customer_id = customer.id;
  }
  return [...byMobile.values()];
}
