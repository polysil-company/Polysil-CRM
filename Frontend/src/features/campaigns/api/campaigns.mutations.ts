"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createCampaign, deleteCampaign, patchCampaign, type WriteInput } from "./campaigns.api";
import { campaignKeys } from "./campaigns.queries";
import type { Campaign, CampaignCreateRequest, CampaignPatchRequest } from "./campaigns.schemas";

function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: campaignKeys.all });
  };
}

/** MKT-005 · Add a campaign. */
export function useCreateCampaign(): UseMutationResult<
  Campaign,
  Error,
  WriteInput<CampaignCreateRequest>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...campaignKeys.all, "create"],
    mutationFn: createCampaign,
    meta: { dataId: "MKT-005" },
    onSuccess: refresh,
  });
}

/** MKT-005 · Change a campaign, or switch it off or on. */
export function usePatchCampaign(): UseMutationResult<
  Campaign,
  Error,
  { readonly campaignId: string } & WriteInput<CampaignPatchRequest>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...campaignKeys.all, "patch"],
    mutationFn: ({ campaignId, ...input }) => patchCampaign(campaignId, input),
    meta: { dataId: "MKT-005" },
    onSuccess: refresh,
  });
}

/** MKT-005 · Delete a campaign nothing names. */
export function useDeleteCampaign(): UseMutationResult<
  undefined,
  Error,
  { readonly campaignId: string; readonly idempotencyKey: string }
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...campaignKeys.all, "delete"],
    mutationFn: ({ campaignId, idempotencyKey }) => deleteCampaign(campaignId, idempotencyKey),
    meta: { dataId: "MKT-005" },
    onSuccess: refresh,
  });
}
