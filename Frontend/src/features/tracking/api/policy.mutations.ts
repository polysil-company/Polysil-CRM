"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { putTrackingPolicy } from "./policy.api";
import { policyKeys } from "./policy.queries";
import type { Policy, PolicyRequest } from "./policy.schemas";
import { visitKeys } from "./visits.queries";

/** TRK-006 · Save a new policy version; refreshes the policy and everyone's tracking setup. */
export function useSaveTrackingPolicy(): UseMutationResult<
  Policy,
  Error,
  { readonly body: PolicyRequest; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...policyKeys.policy(), "save"],
    mutationFn: putTrackingPolicy,
    meta: { dataId: "TRK-006" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: policyKeys.policy() });
      void queryClient.invalidateQueries({ queryKey: visitKeys.config() });
    },
  });
}
