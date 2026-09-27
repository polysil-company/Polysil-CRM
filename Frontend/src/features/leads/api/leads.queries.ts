import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getLead, getLeadStats, getLeadTimeline, listLeads } from "./leads.api";
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
  timeline: (leadId: string) => [...leadKeys.details(), leadId, "timeline"] as const,
  stats: () => [...leadKeys.all, "stats"] as const,
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

/** The counts change slowly and are shown in navigation: one minute is fresh enough. */
export function leadStatsQueryOptions() {
  return queryOptions({
    queryKey: leadKeys.stats(),
    queryFn: ({ signal }) => getLeadStats(signal),
    staleTime: 60_000,
    meta: { dataId: "LEAD-004" },
  });
}

/** The first timeline page has no cursor. Typed here so the page param is `string | null`. */
const NEWEST_TIMELINE_PAGE: string | null = null;

/**
 * LEAD-005 · The timeline, newest first, one page at a time: "Show older" loads the next
 * page with the previous page's cursor. Invalidating the lead's detail key refreshes it too.
 */
export function leadTimelineQueryOptions(leadId: string) {
  return infiniteQueryOptions({
    queryKey: leadKeys.timeline(leadId),
    queryFn: ({ pageParam, signal }) => getLeadTimeline({ leadId, cursor: pageParam }, signal),
    initialPageParam: NEWEST_TIMELINE_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "LEAD-005" },
  });
}
