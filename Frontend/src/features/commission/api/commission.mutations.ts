"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import {
  addCommissionRate,
  decideCommission,
  payCommission,
  recordCommission,
  type CommissionDecision,
  type WriteInput,
} from "./commission.api";
import { commissionKeys } from "./commission.queries";
import type {
  AddRateRequest,
  Commission,
  CommissionRate,
  DecisionRequest,
  PaymentRequest,
  RecordCommissionRequest,
} from "./commission.schemas";

/** Puts the answer on its application and refreshes every list. */
function useSettle(): (commission: Commission) => void {
  const queryClient = useQueryClient();
  return (commission) => {
    queryClient.setQueryData(commissionKeys.live(commission.application.id), commission);
    void queryClient.invalidateQueries({ queryKey: commissionKeys.lists() });
  };
}

/** SUBS-016 · Record stage 18 (or record it again while calculated or returned). */
export function useRecordCommission(): UseMutationResult<
  Commission,
  Error,
  { applicationId: string } & WriteInput<RecordCommissionRequest>
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...commissionKeys.all, "record"],
    mutationFn: ({ applicationId, ...input }) => recordCommission(applicationId, input),
    meta: { dataId: "SUBS-016" },
    onSuccess: settle,
  });
}

/** SUBS-017 · Approve, return or cancel. */
export function useDecideCommission(): UseMutationResult<
  Commission,
  Error,
  { commissionId: string; decision: CommissionDecision } & WriteInput<DecisionRequest>
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...commissionKeys.all, "decide"],
    mutationFn: ({ commissionId, decision, ...input }) =>
      decideCommission(commissionId, decision, input),
    meta: { dataId: "SUBS-017" },
    onSuccess: settle,
  });
}

/** SUBS-017 · Record an approved commission's payment. */
export function usePayCommission(): UseMutationResult<
  Commission,
  Error,
  { commissionId: string } & WriteInput<PaymentRequest>
> {
  const settle = useSettle();
  return useMutation({
    mutationKey: [...commissionKeys.all, "pay"],
    mutationFn: ({ commissionId, ...input }) => payCommission(commissionId, input),
    meta: { dataId: "SUBS-017" },
    onSuccess: settle,
  });
}

/** SUBS-018 · Add a rate; the scheme's list refreshes. */
export function useAddCommissionRate(): UseMutationResult<
  CommissionRate,
  Error,
  WriteInput<AddRateRequest>
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...commissionKeys.all, "add-rate"],
    mutationFn: addCommissionRate,
    meta: { dataId: "SUBS-018" },
    onSuccess: (rate) => {
      void queryClient.invalidateQueries({ queryKey: commissionKeys.rates(rate.scheme) });
      // A new rate can change an application's preview.
      void queryClient.invalidateQueries({ queryKey: commissionKeys.all });
    },
  });
}
