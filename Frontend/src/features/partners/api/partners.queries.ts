import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { getPartner, listPartners, lookupGstin, searchParents } from "./partners.api";
import type { PartnerListParams, PartnerType } from "./partners.schemas";

/**
 * Query keys for channel partners. A change to one partner moves it in the list, and in its
 * parent's list of partners under it, so mutations invalidate `partnerKeys.all`.
 */
export const partnerKeys = {
  all: ["partners"] as const,
  list: (params: Omit<PartnerListParams, "cursor">) =>
    [...partnerKeys.all, "list", params] as const,
  detail: (partnerId: string) => [...partnerKeys.all, "detail", partnerId] as const,
  parents: (type: PartnerType, q: string) => [...partnerKeys.all, "parents", type, q] as const,
  gstin: (gstin: string) => [...partnerKeys.all, "gstin", gstin] as const,
};

const FIRST_PAGE: string | null = null;

/** CHNL-001 · Partners, a page at a time. */
export function partnerListQueryOptions(params: Omit<PartnerListParams, "cursor">) {
  return infiniteQueryOptions({
    queryKey: partnerKeys.list(params),
    queryFn: ({ pageParam, signal }) => listPartners({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "CHNL-001" },
  });
}

/** CHNL-001 · One partner. */
export function partnerDetailQueryOptions(partnerId: string) {
  return queryOptions({
    queryKey: partnerKeys.detail(partnerId),
    queryFn: ({ signal }) => getPartner(partnerId, signal),
    meta: { dataId: "CHNL-001" },
  });
}

/** CHNL-002 · Open partners of one type, for the parent picker. */
export function parentSearchQueryOptions(type: PartnerType, q: string) {
  return queryOptions({
    queryKey: partnerKeys.parents(type, q),
    queryFn: ({ signal }) => searchParents(type, q, signal),
    staleTime: 60_000,
    meta: { dataId: "CHNL-002" },
  });
}

/** CHNL-006 · What the GST record says about a GSTIN. It rarely changes: kept for the session. */
export function gstinLookupQueryOptions(gstin: string) {
  return queryOptions({
    queryKey: partnerKeys.gstin(gstin),
    queryFn: ({ signal }) => lookupGstin(gstin, signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
    meta: { dataId: "CHNL-006" },
  });
}
