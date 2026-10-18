import type { LeadWire } from "@/features/leads/api/leads.schemas";
import { isPartnerRole, PARTNER_ROLES } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";

import { mockMeFor } from "./sessions";

/**
 * The signed-in partner user's own partner, or null for staff. The backend scopes every list a
 * partner user reads to their dealership (`partner_subtree`); the mock does the same here.
 */
export function mockSessionPartnerId(): string | null {
  const role = readMockRole();
  return isPartnerRole(role) ? (mockMeFor(role).data.partner?.id ?? null) : null;
}

/** Whether the signed-in user may see this lead: staff all, a partner user their own. */
export function leadInPartnerScope(lead: LeadWire): boolean {
  return partnerInScope(lead.assigned_partner);
}

/** Whether a record with this partner is in the signed-in user's scope: staff all, a partner user their own. */
export function partnerInScope(partner: { id: string } | null | undefined): boolean {
  const partnerId = mockSessionPartnerId();
  return partnerId === null || partner?.id === partnerId;
}

/** How many seeded leads each demo partner user's dealership holds. */
const LEADS_PER_PARTNER = 8;

/**
 * So a partner user sees a book of their own: a few new or contacted seeded leads with no partner
 * are handed to each demo partner user's dealership.
 */
export function handLeadsToSessionPartners(leads: LeadWire[]): void {
  for (const role of PARTNER_ROLES) {
    const partner = mockMeFor(role).data.partner;
    if (partner === null || partner === undefined) continue;
    // Early leads with no partner yet: they have no quotation, order or customer, so handing
    // them over changes nothing else in the mock.
    const held = leads.filter(
      (lead) =>
        lead.assigned_partner === null && (lead.stage === "new" || lead.stage === "contacted"),
    );
    for (const lead of held.slice(0, LEADS_PER_PARTNER)) {
      // Taken leads now have a partner, so the next role's filter skips them.
      lead.assigned_partner = {
        id: partner.id,
        name: partner.name ?? "Channel partner",
        partner_type: role,
      };
    }
  }
}
