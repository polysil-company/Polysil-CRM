import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { countLeads, getLead, listLeads } from "./leads.api";
import type { LeadListParams } from "./leads.schemas";

/**
 * Query keys for leads. Invalidate by prefix:
 *   leadKeys.all      → everything about leads
 *   leadKeys.lists()  → every list, whatever the filters
 */
export const leadKeys = {
  all: ["leads"] as const,
  lists: () => [...leadKeys.all, "list"] as const,
  list: (params: LeadListParams) => [...leadKeys.lists(), params] as const,
  details: () => [...leadKeys.all, "detail"] as const,
  detail: (leadId: string) => [...leadKeys.details(), leadId] as const,
  count: () => [...leadKeys.all, "count"] as const,
};

/** Keeps the previous page on screen while the next one loads — no skeleton flash on paging. */
export function leadListQueryOptions(params: LeadListParams) {
  return queryOptions({
    queryKey: leadKeys.list(params),
    queryFn: ({ signal }) => listLeads(params, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "LEAD-001" },
  });
}

export function leadDetailQueryOptions(leadId: string) {
  return queryOptions({
    queryKey: leadKeys.detail(leadId),
    queryFn: ({ signal }) => getLead(leadId, signal),
    meta: { dataId: "LEAD-003" },
  });
}

/** The count changes slowly and is shown in navigation: one minute is fresh enough. */
export function leadCountQueryOptions() {
  return queryOptions({
    queryKey: leadKeys.count(),
    queryFn: ({ signal }) => countLeads(signal),
    staleTime: 60_000,
    meta: { dataId: "LEAD-004" },
  });
}
