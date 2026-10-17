import { z } from "zod";

import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  campaignListSchema,
  campaignResponseSchema,
  type Campaign,
  type CampaignCreateRequest,
  type CampaignListParams,
  type CampaignPatchRequest,
} from "./campaigns.schemas";

const log = createLogger({ file: "features/campaigns/api/campaigns.api.ts", dataId: "MKT-005" });

export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

/** MKT-005, MKT-006 · Campaigns, newest start first, at most 500. Any staff user; 403 for partners. */
export function listCampaigns(
  params: CampaignListParams,
  signal?: AbortSignal,
): Promise<Campaign[]> {
  return apiRequest({
    dataId: "MKT-005",
    logger: log,
    fn: "listCampaigns",
    path: "/campaigns",
    query: {
      active: params.active === null ? undefined : String(params.active),
      type: params.type ?? undefined,
      q: params.q === "" ? undefined : params.q,
    },
    schema: campaignListSchema,
    signal,
  });
}

/** MKT-005 · One campaign with its summary: leads, wins, sales and cost per lead. */
export function getCampaign(campaignId: string, signal?: AbortSignal): Promise<Campaign> {
  return apiRequest({
    dataId: "MKT-005",
    logger: log,
    fn: "getCampaign",
    path: `/campaigns/${encodeURIComponent(campaignId)}`,
    schema: campaignResponseSchema,
    signal,
  });
}

/** MKT-005 · Add a campaign (campaigns.create). 409 campaign_name_taken, case ignored. */
export function createCampaign({
  body,
  idempotencyKey,
}: WriteInput<CampaignCreateRequest>): Promise<Campaign> {
  return apiRequest({
    dataId: "MKT-005",
    logger: log,
    fn: "createCampaign",
    method: "POST",
    path: "/campaigns",
    body,
    idempotencyKey,
    schema: campaignResponseSchema,
  });
}

/** MKT-005 · Change a campaign or switch it off (campaigns.edit). Null clears an optional field. */
export function patchCampaign(
  campaignId: string,
  { body, idempotencyKey }: WriteInput<CampaignPatchRequest>,
): Promise<Campaign> {
  return apiRequest({
    dataId: "MKT-005",
    logger: log,
    fn: "patchCampaign",
    method: "PATCH",
    path: `/campaigns/${encodeURIComponent(campaignId)}`,
    body,
    idempotencyKey,
    schema: campaignResponseSchema,
  });
}

/** MKT-005 · Delete a campaign nothing names (campaigns.delete); 409 campaign_in_use otherwise. */
export function deleteCampaign(campaignId: string, idempotencyKey: string): Promise<undefined> {
  return apiRequest({
    dataId: "MKT-005",
    logger: log,
    fn: "deleteCampaign",
    method: "DELETE",
    path: `/campaigns/${encodeURIComponent(campaignId)}`,
    idempotencyKey,
    schema: z.undefined(),
  });
}
