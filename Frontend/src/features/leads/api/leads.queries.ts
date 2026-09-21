import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getLead, getLeadSummary, listLeads } from "./leads.api";
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
  summary: () => [...leadKeys.all, "summary"] as const,
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

/** Counts change slowly and are shown in navigation: one minute is fresh enough. */
export function leadSummaryQueryOptions() {
  return queryOptions({
    queryKey: leadKeys.summary(),
    queryFn: ({ signal }) => getLeadSummary(signal),
    staleTime: 60_000,
    meta: { dataId: "LEAD-004" },
  });
}
