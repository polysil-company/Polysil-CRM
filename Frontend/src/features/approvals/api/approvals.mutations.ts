"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { quotationKeys } from "@/features/quotations/api/quotations.queries";

import { decideApprovalStep } from "./approvals.api";
import { approvalKeys } from "./approvals.queries";
import type { DecisionRequest, DecisionResult } from "./approvals.schemas";

export interface DecideInput {
  readonly stepId: string;
  readonly body: DecisionRequest;
  readonly idempotencyKey: string;
}

/**
 * APPR-001 · Approve or reject a step. The inbox and badge refetch, and a decided quotation
 * is re-read, so its page shows Send (approved) or the refusal (returned).
 */
export function useDecideApproval(): UseMutationResult<DecisionResult, Error, DecideInput> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...approvalKeys.all, "decide"],
    mutationFn: ({ stepId, body, idempotencyKey }) =>
      decideApprovalStep(stepId, { body, idempotencyKey }),
    meta: { dataId: "APPR-001" },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: approvalKeys.all });
    },
    onSuccess: (result) => {
      if (result.docType === "quotation") {
        void queryClient.invalidateQueries({ queryKey: quotationKeys.detail(result.id) });
        void queryClient.invalidateQueries({ queryKey: quotationKeys.timelines() });
      }
    },
  });
}
