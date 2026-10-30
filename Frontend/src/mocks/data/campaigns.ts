import type { CampaignWire } from "@/features/campaigns/api/campaigns.schemas";
import type { LeadWire } from "@/features/leads/api/leads.schemas";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";

import { mockUuid } from "./reference";
import { MOCK_TERRITORIES } from "./territories";

/** The mock's own id space for campaigns. */
const CAMPAIGN_SPACE = 0xca7;

export function mockCampaignId(index: number): string {
  return mockUuid(CAMPAIGN_SPACE, index);
}

/** A campaign as the mock keeps it: without the counts and summary it works out per call. */
export type MockCampaign = Omit<CampaignWire, "lead_count" | "summary">;

function districtRef(name: string): CampaignWire["territory"] {
  const found = MOCK_TERRITORIES.find((item) => item.level === "district" && item.name === name);
  return found === undefined ? null : { id: found.id, name: found.name, level: found.level };
}

/**
 * Four campaigns: a fair running now, a farmer meeting last month with its actual cost, a digital
 * drive with no place, and one switched off. Every eighth lead names the fair; every eleventh the
 * meeting.
 */
export function seedCampaigns(): MockCampaign[] {
  const today = todayInIndia();
  const at = `${shiftCalendarDay(today, -40)}T05:30:00.000Z`;
  return [
    {
      id: mockCampaignId(1),
      name: "Krishi Mela Rajkot 2026",
      type: "agri_fair",
      territory: districtRef("Rajkot"),
      start_date: shiftCalendarDay(today, -2),
      end_date: shiftCalendarDay(today, 1),
      cost_planned: "150000.00",
      cost_actual: null,
      description: "Stall 14, with drip demos twice a day.",
      is_active: true,
      created_at: at,
      updated_at: at,
    },
    {
      id: mockCampaignId(2),
      name: "Anand farmer meeting",
      type: "farmer_meeting",
      territory: districtRef("Anand"),
      start_date: shiftCalendarDay(today, -30),
      end_date: null,
      cost_planned: "25000.00",
      cost_actual: "21800.00",
      description: null,
      is_active: true,
      created_at: at,
      updated_at: at,
    },
    {
      id: mockCampaignId(3),
      name: "Kharif WhatsApp drive",
      type: "digital",
      territory: null,
      start_date: shiftCalendarDay(today, -60),
      end_date: shiftCalendarDay(today, -15),
      cost_planned: "40000.00",
      cost_actual: "38250.00",
      description: "Broadcast to past enquiries, with the drip subsidy leaflet.",
      is_active: true,
      created_at: at,
      updated_at: at,
    },
    {
      id: mockCampaignId(4),
      name: "Bhavnagar dealer meet 2025",
      type: "dealer_meet",
      territory: districtRef("Bhavnagar"),
      start_date: shiftCalendarDay(today, -320),
      end_date: shiftCalendarDay(today, -319),
      cost_planned: "60000.00",
      cost_actual: "64500.00",
      description: null,
      is_active: false,
      created_at: at,
      updated_at: at,
    },
  ];
}

/** Puts the seeded campaigns on some leads, in place. A dealer's leads carry none. */
export function tagLeadsWithCampaigns(leads: LeadWire[], campaigns: readonly MockCampaign[]): void {
  const [fair, meeting] = campaigns;
  leads.forEach((lead, index) => {
    if (lead.source === "dealer") return;
    const campaign = index % 8 === 0 ? fair : index % 11 === 0 ? meeting : undefined;
    if (campaign === undefined) return;
    lead.campaign_id = campaign.id;
    lead.campaign_name = campaign.name;
  });
}
