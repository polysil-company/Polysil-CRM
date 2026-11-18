import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import {
  getCommissionPreview,
  getLiveCommission,
  listCommissionRates,
  listCommissions,
} from "./commission.api";
import type { CommissionListParams } from "./commission.schemas";

/**
 * Query keys for dealer commissions. Invalidate by prefix:
 *   commissionKeys.all → everything about commissions
 */
export const commissionKeys = {
  all: ["commission"] as const,
  lists: () => [...commissionKeys.all, "list"] as const,
  list: (params: CommissionListParams) => [...commissionKeys.lists(), params] as const,
  application: (applicationId: string) =>
    [...commissionKeys.all, "application", applicationId] as const,
  live: (applicationId: string) => [...commissionKeys.application(applicationId), "live"] as const,
  preview: (applicationId: string) =>
    [...commissionKeys.application(applicationId), "preview"] as const,
  rates: (scheme: string) => [...commissionKeys.all, "rates", scheme] as const,
};

const FIRST_PAGE: string | null = null;

/** SUBS-016 · The live commission on an application (404 when none). */
export function liveCommissionQueryOptions(applicationId: string) {
  return queryOptions({
    queryKey: commissionKeys.live(applicationId),
    queryFn: ({ signal }) => getLiveCommission(applicationId, signal),
    // A 404 is the answer "none yet", not a failure to retry.
    retry: false,
    meta: { dataId: "SUBS-016" },
  });
}

/** SUBS-016 · Stage 18's starting figures and rate. */
export function commissionPreviewQueryOptions(applicationId: string) {
  return queryOptions({
    queryKey: commissionKeys.preview(applicationId),
    queryFn: ({ signal }) => getCommissionPreview(applicationId, signal),
    retry: false,
    meta: { dataId: "SUBS-016" },
  });
}

/** SUBS-017 · The commission report by status, a page at a time. */
export function commissionListQueryOptions(params: CommissionListParams) {
  return infiniteQueryOptions({
    queryKey: commissionKeys.list(params),
    queryFn: ({ pageParam, signal }) => listCommissions({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (page) => page.nextCursor,
    placeholderData: keepPreviousData,
    meta: { dataId: "SUBS-017" },
  });
}

/** SUBS-018 · A scheme's commission rates. */
export function commissionRatesQueryOptions(scheme: string) {
  return queryOptions({
    queryKey: commissionKeys.rates(scheme),
    queryFn: ({ signal }) => listCommissionRates(scheme, signal),
    meta: { dataId: "SUBS-018" },
  });
}
