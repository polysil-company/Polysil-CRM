"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import {
  adjustPoints,
  createGift,
  createRule,
  decideRedemption,
  patchGift,
  patchRule,
  putRewardSettings,
  redeemOnOrder,
  removeFromOrder,
  requestGift,
  type RedemptionDecision,
  type WriteInput,
} from "./rewards.api";
import { rewardKeys } from "./rewards.queries";
import type {
  AdjustmentRequest,
  Gift,
  GiftCreateRequest,
  GiftPatchRequest,
  LedgerRow,
  Redemption,
  RewardRule,
  RewardSettings,
  RuleCreateRequest,
  RulePatchRequest,
  SettingsRequest,
} from "./rewards.schemas";

/** A redemption moves points: refresh the balances, histories and redemption lists. */
function useRefreshPoints(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: rewardKeys.holder() });
    void queryClient.invalidateQueries({ queryKey: rewardKeys.redemptions() });
  };
}

/** RWD-001 · Ask for a gift. */
export function useRequestGift(): UseMutationResult<
  Redemption,
  Error,
  WriteInput<{ readonly gift_id: string }>
> {
  const refresh = useRefreshPoints();
  return useMutation({
    mutationKey: [...rewardKeys.all, "request-gift"],
    mutationFn: requestGift,
    meta: { dataId: "RWD-001" },
    onSuccess: refresh,
  });
}

/** RWD-001 withdraw, RWD-002 fulfil and reject. */
export function useDecideRedemption(): UseMutationResult<
  Redemption,
  Error,
  { redemptionId: string; decision: RedemptionDecision } & WriteInput<{
    readonly remark: string | null;
  }>
> {
  const refresh = useRefreshPoints();
  return useMutation({
    mutationKey: [...rewardKeys.all, "decide"],
    mutationFn: ({ redemptionId, decision, ...input }) =>
      decideRedemption(redemptionId, decision, input),
    meta: { dataId: "RWD-002" },
    onSuccess: refresh,
  });
}

/** RWD-003 · Add or take away points by hand. */
export function useAdjustPoints(): UseMutationResult<
  LedgerRow,
  Error,
  WriteInput<AdjustmentRequest>
> {
  const refresh = useRefreshPoints();
  return useMutation({
    mutationKey: [...rewardKeys.all, "adjust"],
    mutationFn: adjustPoints,
    meta: { dataId: "RWD-003" },
    onSuccess: refresh,
  });
}

/** RWD-003 · Add a rule, or change one. */
export function useSaveRule(): UseMutationResult<
  RewardRule,
  Error,
  | ({ ruleId: null } & WriteInput<RuleCreateRequest>)
  | ({ ruleId: string } & WriteInput<RulePatchRequest>)
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...rewardKeys.all, "save-rule"],
    mutationFn: (input) =>
      input.ruleId === null
        ? createRule({ body: input.body, idempotencyKey: input.idempotencyKey })
        : patchRule(input.ruleId, { body: input.body, idempotencyKey: input.idempotencyKey }),
    meta: { dataId: "RWD-003" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: rewardKeys.rules() });
    },
  });
}

/** RWD-003 · Change the point value or the limit. */
export function useSaveRewardSettings(): UseMutationResult<
  RewardSettings,
  Error,
  WriteInput<SettingsRequest>
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...rewardKeys.all, "settings"],
    mutationFn: putRewardSettings,
    meta: { dataId: "RWD-003" },
    onSuccess: (settings) => {
      queryClient.setQueryData(rewardKeys.settings(), settings);
      // A balance shows what its points are worth.
      void queryClient.invalidateQueries({ queryKey: rewardKeys.holder() });
    },
  });
}

/** RWD-003 · Add a gift, or change one. */
export function useSaveGift(): UseMutationResult<
  Gift,
  Error,
  | ({ giftId: null } & WriteInput<GiftCreateRequest>)
  | ({ giftId: string } & WriteInput<GiftPatchRequest>)
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...rewardKeys.all, "save-gift"],
    mutationFn: (input) =>
      input.giftId === null
        ? createGift({ body: input.body, idempotencyKey: input.idempotencyKey })
        : patchGift(input.giftId, { body: input.body, idempotencyKey: input.idempotencyKey }),
    meta: { dataId: "RWD-003" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...rewardKeys.all, "gifts"] });
    },
  });
}

/** RWD-004 · Put points on a draft order, or take them off. */
export function useOrderPoints(): UseMutationResult<
  Redemption | null,
  Error,
  { orderId: string; points: number | null; idempotencyKey: string }
> {
  const refresh = useRefreshPoints();
  return useMutation({
    mutationKey: [...rewardKeys.all, "order-points"],
    mutationFn: async ({ orderId, points, idempotencyKey }) => {
      if (points === null) {
        await removeFromOrder(orderId, idempotencyKey);
        return null;
      }
      return redeemOnOrder(orderId, { body: { points }, idempotencyKey });
    },
    meta: { dataId: "RWD-004" },
    onSuccess: refresh,
  });
}
