import type { LeadWire } from "@/features/leads/api/leads.schemas";
import type { PartnerType } from "@/features/partners/api/partners.schemas";
import { isPartnerRole, PARTNER_ROLES } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";

import type { MockPartnerRecord } from "./partners";
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

/**
 * CHNL-002 · The demo partner users' own dealerships as partner records, so a dealer can open
 * its own page and add sub-dealers under it: the distributor at the top, the dealer under it,
 * the sub-dealer under the dealer. They take the first seeded district.
 */
export function sessionPartnerRecords(
  territory: MockPartnerRecord["territory"],
): MockPartnerRecord[] {
  const records: MockPartnerRecord[] = [];
  let above: MockPartnerRecord | null = null;
  for (const [index, role] of PARTNER_ROLES.entries()) {
    const partner = mockMeFor(role).data.partner;
    if (partner === null || partner === undefined) continue;
    const type: PartnerType = role;
    const record: MockPartnerRecord = {
      id: partner.id,
      code: `CP-${String(901 + index)}`,
      name: partner.name ?? "Channel partner",
      partner_type: type,
      price_tier: type,
      parent_id: above?.id ?? null,
      parent:
        above === null
          ? null
          : { id: above.id, name: above.name, partner_type: above.partner_type },
      territory,
      contact_name: mockMeFor(role).data.full_name,
      mobile: `91982509${String(9001 + index)}`,
      email: null,
      address: "Station Road, Rajkot, Gujarat",
      gstin: null,
      pan: null,
      is_gst_registered: false,
      credit_limit: null,
      payment_terms_days: null,
      is_active: true,
      created_at: "2026-03-01T05:30:00Z",
    };
    records.push(record);
    above = record;
  }
  return records;
}

/**
 * The partners a user may see: staff every one, a partner user its own record and every
 * partner below it, as the backend scopes `GET /partners` (`partner_subtree`).
 */
export function partnerRecordInScope(
  record: { id: string; parent_id: string | null },
  partners: readonly { id: string; parent_id: string | null }[],
): boolean {
  const mine = mockSessionPartnerId();
  if (mine === null) return true;
  let current: { id: string; parent_id: string | null } | undefined = record;
  for (let hops = 0; current !== undefined && hops < 5; hops += 1) {
    if (current.id === mine) return true;
    const parentId: string | null = current.parent_id;
    current = parentId === null ? undefined : partners.find((item) => item.id === parentId);
  }
  return false;
}
