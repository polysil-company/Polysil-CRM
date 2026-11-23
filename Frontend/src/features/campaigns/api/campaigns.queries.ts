import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getCampaign, listCampaigns } from "./campaigns.api";
import type { CampaignListParams } from "./campaigns.schemas";

/**
 * Query keys for campaigns. Invalidate by prefix:
 *   campaignKeys.all → every list (the pickers too) and every campaign
 */
export const campaignKeys = {
  all: ["campaigns"] as const,
  list: (params: CampaignListParams) => [...campaignKeys.all, "list", params] as const,
  one: (campaignId: string) => [...campaignKeys.all, "one", campaignId] as const,
};

/** MKT-005 · Campaigns matching the filters. */
export function campaignListQueryOptions(params: CampaignListParams) {
  return queryOptions({
    queryKey: campaignKeys.list(params),
    queryFn: ({ signal }) => listCampaigns(params, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "MKT-005" },
  });
}

/** MKT-006 · The active campaigns, for the pickers on a lead or a QR code. */
export function activeCampaignsQueryOptions() {
  return queryOptions({
    queryKey: campaignKeys.list({ active: true, type: null, q: "" }),
    queryFn: ({ signal }) => listCampaigns({ active: true, type: null, q: "" }, signal),
    staleTime: 5 * 60_000,
    meta: { dataId: "MKT-006" },
  });
}

/** MKT-005 · One campaign with its summary. */
export function campaignQueryOptions(campaignId: string) {
  return queryOptions({
    queryKey: campaignKeys.one(campaignId),
    queryFn: ({ signal }) => getCampaign(campaignId, signal),
    meta: { dataId: "MKT-005" },
  });
}
