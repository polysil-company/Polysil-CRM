import type { CampaignType } from "@/features/campaigns/api/campaigns.schemas";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";

export const CAMPAIGN_TYPE_LABELS: Readonly<Record<CampaignType, string>> = {
  exhibition: "Exhibition",
  agri_fair: "Agri fair",
  farmer_meeting: "Farmer meeting",
  dealer_meet: "Dealer meet",
  promo_drive: "Promotion drive",
  digital: "Digital",
  print: "Print",
  other: "Other",
};

/** "12 Oct 2026", or "12 Oct 2026 to 14 Oct 2026"; an end date equal to the start is one day. */
export function campaignDates(start: string, end: string | null): string {
  return end === null || end === start
    ? formatBusinessDay(start)
    : `${formatBusinessDay(start)} to ${formatBusinessDay(end)}`;
}
