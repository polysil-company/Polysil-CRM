"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { userKeys } from "@/features/users/api/users.queries";

import { createPartner, patchPartner, setPartnerOpen } from "./partners.api";
import { partnerKeys } from "./partners.queries";
import type { Partner, PartnerStateChange } from "./partners.schemas";

function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: partnerKeys.all });
  };
}

/** CHNL-002 · Add a distributor, or a dealer or sub-dealer under one. */
export function useCreatePartner(): UseMutationResult<
  Partner,
  Error,
  Parameters<typeof createPartner>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...partnerKeys.all, "create"],
    mutationFn: createPartner,
    meta: { dataId: "CHNL-002" },
    onSuccess: refresh,
  });
}

/** CHNL-003 · Correct a partner. */
export function usePatchPartner(): UseMutationResult<
  Partner,
  Error,
  Parameters<typeof patchPartner>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...partnerKeys.all, "patch"],
    mutationFn: patchPartner,
    meta: { dataId: "CHNL-003" },
    onSuccess: refresh,
  });
}

/** CHNL-004 · Close or reopen a partner. Its users change too, so people refresh as well. */
export function useSetPartnerOpen(): UseMutationResult<
  PartnerStateChange,
  Error,
  Parameters<typeof setPartnerOpen>[0]
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...partnerKeys.all, "state"],
    mutationFn: setPartnerOpen,
    meta: { dataId: "CHNL-004" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: partnerKeys.all });
      void queryClient.invalidateQueries({ queryKey: userKeys.all });
    },
  });
}
