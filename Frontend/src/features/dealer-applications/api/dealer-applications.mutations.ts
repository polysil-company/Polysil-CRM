"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { partnerKeys } from "@/features/partners/api/partners.queries";

import {
  createDealerApplication,
  decideDealerApplication,
  patchDealerApplication,
  renewDealerApplicationLink,
  submitDealerApplication,
  withdrawDealerApplication,
} from "./dealer-applications.api";
import { dealerApplicationKeys } from "./dealer-applications.queries";
import type { DealerApplication } from "./dealer-applications.schemas";

/**
 * Every write answers the application: it replaces the cached one (keeping an `apply_url`
 * the answer carries for the screen to show), and the list refreshes.
 */
function useApply(): (application: DealerApplication) => void {
  const queryClient = useQueryClient();
  return (application) => {
    queryClient.setQueryData(dealerApplicationKeys.detail(application.id), application);
    void queryClient.invalidateQueries({
      queryKey: [...dealerApplicationKeys.all, "list"],
    });
  };
}

type Mutation<TFn extends (input: never) => Promise<DealerApplication>> = UseMutationResult<
  DealerApplication,
  Error,
  Parameters<TFn>[0]
>;

/** CHNL-007 · Start an application. */
export function useCreateDealerApplication(): Mutation<typeof createDealerApplication> {
  const apply = useApply();
  return useMutation({
    mutationKey: [...dealerApplicationKeys.all, "create"],
    mutationFn: createDealerApplication,
    meta: { dataId: "CHNL-007" },
    onSuccess: apply,
  });
}

/** CHNL-007 · Fill or correct fields for the applicant. */
export function usePatchDealerApplication(): Mutation<typeof patchDealerApplication> {
  const apply = useApply();
  return useMutation({
    mutationKey: [...dealerApplicationKeys.all, "patch"],
    mutationFn: patchDealerApplication,
    meta: { dataId: "CHNL-007" },
    onSuccess: apply,
  });
}

/** CHNL-007 · Submit for the applicant. */
export function useSubmitDealerApplication(): Mutation<typeof submitDealerApplication> {
  const apply = useApply();
  return useMutation({
    mutationKey: [...dealerApplicationKeys.all, "submit"],
    mutationFn: submitDealerApplication,
    meta: { dataId: "CHNL-007" },
    onSuccess: apply,
  });
}

/** CHNL-007 · Withdraw an open application. */
export function useWithdrawDealerApplication(): Mutation<typeof withdrawDealerApplication> {
  const apply = useApply();
  return useMutation({
    mutationKey: [...dealerApplicationKeys.all, "withdraw"],
    mutationFn: withdrawDealerApplication,
    meta: { dataId: "CHNL-007" },
    onSuccess: apply,
  });
}

/** CHNL-007 · A new link; the old one stops. */
export function useRenewDealerApplicationLink(): Mutation<typeof renewDealerApplicationLink> {
  const apply = useApply();
  return useMutation({
    mutationKey: [...dealerApplicationKeys.all, "renew"],
    mutationFn: renewDealerApplicationLink,
    meta: { dataId: "CHNL-007" },
    onSuccess: apply,
  });
}

/** CHNL-007 · Approve, return or reject. Approving adds a dealer, so partners refresh too. */
export function useDecideDealerApplication(): Mutation<typeof decideDealerApplication> {
  const apply = useApply();
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...dealerApplicationKeys.all, "decide"],
    mutationFn: decideDealerApplication,
    meta: { dataId: "CHNL-007" },
    onSuccess: (application) => {
      apply(application);
      void queryClient.invalidateQueries({ queryKey: partnerKeys.all });
    },
  });
}
