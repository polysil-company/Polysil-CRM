import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import {
  getBalance,
  getLedger,
  getRewardSettings,
  listGifts,
  listRedemptions,
  listRules,
} from "./rewards.api";
import type { HolderQuery, RedemptionListParams } from "./rewards.schemas";

/**
 * Query keys for reward points. Invalidate by prefix:
 *   rewardKeys.all     → everything about points
 *   rewardKeys.holder() → every balance and history
 */
export const rewardKeys = {
  all: ["rewards"] as const,
  holder: () => [...rewardKeys.all, "holder"] as const,
  balance: (holder: HolderQuery) => [...rewardKeys.holder(), "balance", holder] as const,
  ledger: (holder: HolderQuery) => [...rewardKeys.holder(), "ledger", holder] as const,
  settings: () => [...rewardKeys.all, "settings"] as const,
  gifts: (activeOnly: boolean) => [...rewardKeys.all, "gifts", activeOnly] as const,
  redemptions: () => [...rewardKeys.all, "redemptions"] as const,
  redemptionList: (params: RedemptionListParams) => [...rewardKeys.redemptions(), params] as const,
  rules: () => [...rewardKeys.all, "rules"] as const,
};

const FIRST_PAGE: string | null = null;

/** RWD-001 · A balance. */
export function balanceQueryOptions(holder: HolderQuery) {
  return queryOptions({
    queryKey: rewardKeys.balance(holder),
    queryFn: ({ signal }) => getBalance(holder, signal),
    meta: { dataId: "RWD-001" },
  });
}

/** RWD-001 · A balance's history, a page at a time. */
export function ledgerQueryOptions(holder: HolderQuery) {
  return infiniteQueryOptions({
    queryKey: rewardKeys.ledger(holder),
    queryFn: ({ pageParam, signal }) => getLedger(holder, pageParam, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (page) => page.nextCursor,
    meta: { dataId: "RWD-001" },
  });
}

/** RWD-001 · What a point is worth, and the order limit. */
export function rewardSettingsQueryOptions() {
  return queryOptions({
    queryKey: rewardKeys.settings(),
    queryFn: ({ signal }) => getRewardSettings(signal),
    meta: { dataId: "RWD-001" },
  });
}

/** RWD-001, RWD-003 · The gifts: the active ones, or all of them for the admin. */
export function giftsQueryOptions(activeOnly: boolean) {
  return queryOptions({
    queryKey: rewardKeys.gifts(activeOnly),
    queryFn: ({ signal }) => listGifts(activeOnly, signal),
    meta: { dataId: "RWD-001" },
  });
}

/** RWD-001, RWD-002 · Redemptions by status. */
export function redemptionsQueryOptions(params: RedemptionListParams) {
  return infiniteQueryOptions({
    queryKey: rewardKeys.redemptionList(params),
    queryFn: ({ pageParam, signal }) => listRedemptions({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (page) => page.nextCursor,
    placeholderData: keepPreviousData,
    meta: { dataId: "RWD-002" },
  });
}

/** RWD-003 · The earning rules. */
export function rulesQueryOptions() {
  return queryOptions({
    queryKey: rewardKeys.rules(),
    queryFn: ({ signal }) => listRules(signal),
    meta: { dataId: "RWD-003" },
  });
}
