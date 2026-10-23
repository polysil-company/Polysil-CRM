import type { PartnerType, PartnerWire } from "@/features/partners/api/partners.schemas";

import { MOCK_PARTNERS } from "./reference";
import { MOCK_TERRITORIES } from "./territories";

/**
 * CHNL-001 · The channel partners as the mock keeps them: the shared seed (`MOCK_PARTNERS`,
 * which leads, orders and users point at) with what the partner admin shows. Codes are the
 * seed's place, `CP-001`, as `/lookups/partners` names them. Invented businesses.
 */
export interface MockPartnerRecord extends Omit<PartnerWire, "users" | "partner_type"> {
  readonly partner_type: PartnerType;
  parent_id: string | null;
}

/** Who sits under whom in the seed, by index: dealers under their district's distributor. */
const PARENT_INDEX: Readonly<Record<number, number>> = {
  2: 0, // Shree Ganesh Agro Agency under Saurashtra Agro Distributors
  3: 0, // Khodiyar Irrigation under Saurashtra Agro Distributors
  4: 1, // Patel Agro Traders under Sorath Agri Distributors
  5: 0, // Ambika Krishi Kendra under Saurashtra Agro Distributors
  6: 2, // Virpur Agro Point under Shree Ganesh Agro Agency
  7: 4, // Balagam Krishi Seva under Patel Agro Traders
  8: 5, // Babra Farm Supplies under Ambika Krishi Kendra
};

const PARTNER_TYPES_SEEDED: readonly PartnerType[] = ["distributor", "dealer", "sub_dealer"];

function typeOf(value: string): PartnerType {
  return PARTNER_TYPES_SEEDED.find((type) => type === value) ?? "dealer";
}

export function mockPartnerCode(index: number): string {
  return `CP-${String(index + 1).padStart(3, "0")}`;
}

export function seedPartners(): MockPartnerRecord[] {
  const records = MOCK_PARTNERS.map((partner, index): MockPartnerRecord => {
    const district = MOCK_TERRITORIES.find(
      (territory) => territory.level === "district" && territory.name === partner.district,
    );
    const distributor = partner.partner_type === "distributor";
    return {
      id: partner.id,
      code: mockPartnerCode(index),
      name: partner.name,
      partner_type: typeOf(partner.partner_type),
      price_tier: partner.partner_type,
      parent_id: null,
      parent: null,
      territory:
        district === undefined
          ? null
          : { id: district.id, name: district.name, level: district.level },
      contact_name: partner.contact_person,
      mobile: `9198250${String(61000 + index * 173).padStart(5, "0")}`,
      email: distributor ? `accounts${String(index + 1)}@example.in` : null,
      address: `Main Bazar, ${partner.district}, Gujarat`,
      gstin: distributor ? `24AABCS${String(1200 + index)}K1Z${String(index + 1)}` : null,
      pan: distributor ? `AABCS${String(1200 + index)}K` : null,
      is_gst_registered: distributor,
      credit_limit: distributor ? "500000.00" : index % 2 === 0 ? "150000.00" : null,
      payment_terms_days: distributor ? 45 : index % 2 === 0 ? 30 : null,
      // One closed sub-dealer with no users, so the Status filter and Reopen have one to show.
      is_active: index !== 7,
      created_at: `2026-0${String(4 + Math.floor(index / 3))}-${String(10 + index).padStart(2, "0")}T05:30:00Z`,
    };
  });
  for (const [child, parent] of Object.entries(PARENT_INDEX)) {
    const record = records[Number(child)];
    const above = records[parent];
    if (record !== undefined && above !== undefined) {
      record.parent_id = above.id;
      record.parent = { id: above.id, name: above.name, partner_type: above.partner_type };
    }
  }
  // Newest first, as the backend lists them.
  return records.reverse();
}
