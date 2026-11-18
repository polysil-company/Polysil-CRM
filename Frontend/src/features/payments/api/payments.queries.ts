import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getPartnerCredit, getPartnerLedger, listPayments } from "./payments.api";
import type { PaymentListParams } from "./payments.schemas";

/**
 * Query keys for payments. Invalidate by prefix:
 *   paymentKeys.all → every receipt list, ledger and credit
 */
export const paymentKeys = {
  all: ["payments"] as const,
  lists: () => [...paymentKeys.all, "list"] as const,
  list: (params: PaymentListParams) => [...paymentKeys.lists(), params] as const,
  ledger: (partnerId: string, from: string | null, to: string | null) =>
    [...paymentKeys.all, "ledger", partnerId, from, to] as const,
  credit: (partnerId: string) => [...paymentKeys.all, "credit", partnerId] as const,
};

const FIRST_PAGE: string | null = null;

/** ACCT-003 · Receipts, a page at a time. */
export function paymentListQueryOptions(params: PaymentListParams) {
  return infiniteQueryOptions({
    queryKey: paymentKeys.list(params),
    queryFn: ({ pageParam, signal }) => listPayments({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (page) => page.nextCursor,
    placeholderData: keepPreviousData,
    meta: { dataId: "ACCT-003" },
  });
}

/** ACCT-005 · A dealer's ledger for a date range (either end may be open). */
export function partnerLedgerQueryOptions(
  partnerId: string,
  from: string | null,
  to: string | null,
) {
  return queryOptions({
    queryKey: paymentKeys.ledger(partnerId, from, to),
    queryFn: ({ signal }) => getPartnerLedger(partnerId, { from, to }, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "ACCT-005" },
  });
}

/** ACCT-005 · A dealer's credit standing. A 403 means it isn't shown to this reader. */
export function partnerCreditQueryOptions(partnerId: string) {
  return queryOptions({
    queryKey: paymentKeys.credit(partnerId),
    queryFn: ({ signal }) => getPartnerCredit(partnerId, signal),
    retry: false,
    meta: { dataId: "ACCT-005" },
  });
}
