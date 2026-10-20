"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createPortalRating, patchPortalConsent } from "./portal.api";
import { portalKeys } from "./portal.queries";
import type { PortalMe, PortalRating, PortalRatingRequest } from "./portal.schemas";

/** FARM-002 · Record or withdraw consent; the answer is the farmer's details as they now stand. */
export function usePortalConsent(): UseMutationResult<
  PortalMe,
  Error,
  { readonly consentGiven: boolean; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...portalKeys.all, "consent"],
    mutationFn: patchPortalConsent,
    meta: { dataId: "FARM-002" },
    onSuccess: (me) => {
      queryClient.setQueryData(portalKeys.me(), me);
    },
  });
}

/** FARM-003 · Rate an installation or a service; refreshes his ratings. */
export function useCreatePortalRating(): UseMutationResult<
  PortalRating,
  Error,
  { readonly body: PortalRatingRequest; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...portalKeys.all, "rate"],
    mutationFn: createPortalRating,
    meta: { dataId: "FARM-003" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: portalKeys.ratings() });
    },
  });
}
