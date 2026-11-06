import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import { searchTerritories } from "@/features/lookups/api/lookups.api";

import {
  getLead,
  getLeadStats,
  getLeadTimeline,
  listAssignees,
  listDuplicates,
  listLeadAreas,
  listLeads,
  searchPartners,
} from "./leads.api";
import {
  LEAD_AREA_LEVELS,
  type LeadAreaLevel,
  type LeadAreasParams,
  type LeadListParams,
} from "./leads.schemas";

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
  assignees: () => [...leadKeys.all, "assignees"] as const,
  partners: (q: string) => [...leadKeys.all, "partners", q] as const,
  areaRows: (source: AreaSource, params: LeadAreasParams) =>
    [...leadKeys.all, "area-rows", source, params] as const,
  duplicates: () => [...leadKeys.all, "duplicates"] as const,
};

const FIRST_DUPLICATES: string | null = null;

/** LEAD-012 · The duplicate review queue, a page at a time. */
export function duplicatesQueryOptions() {
  return infiniteQueryOptions({
    queryKey: leadKeys.duplicates(),
    queryFn: ({ pageParam, signal }) => listDuplicates(pageParam, signal),
    initialPageParam: FIRST_DUPLICATES,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "LEAD-012" },
  });
}

/** Where an area filter's rows come from: areas holding leads (with counts), or every territory. */
export type AreaSource = "leads" | "territories";

/** One row of an area filter: a state, district or taluka, and how many leads, when known. */
export interface AreaRow {
  readonly id: string;
  readonly name: string;
  readonly level: LeadAreaLevel;
  readonly count: number | null;
}

function isAreaLevel(level: string): level is LeadAreaLevel {
  return LEAD_AREA_LEVELS.some((item) => item === level);
}

/**
 * LEAD-001, MSTR-002 · One level of an area filter. The lead list counts its leads in each area
 * (`GET /leads/areas`); other lists, such as orders, drill through the territory tree
 * (`GET /lookups/territories?parent_id=`), which has no counts. Both give the same rows.
 */
export function areaRowsQueryOptions(source: AreaSource, params: LeadAreasParams) {
  return queryOptions({
    queryKey: leadKeys.areaRows(source, params),
    queryFn: async ({ signal }): Promise<AreaRow[]> => {
      if (source === "leads") {
        const areas = await listLeadAreas(params, signal);
        return areas.map((area) => ({
          id: area.id,
          name: area.name,
          level: area.level,
          count: area.leadCount,
        }));
      }
      const territories = await searchTerritories(
        { q: "", level: params.level, levels: null, limit: 100, parentId: params.parentId },
        signal,
      );
      return territories.flatMap((territory) =>
        isAreaLevel(territory.level)
          ? [{ id: territory.id, name: territory.name, level: territory.level, count: null }]
          : [],
      );
    },
    staleTime: 5 * 60_000,
    meta: { dataId: source === "leads" ? "LEAD-001" : "MSTR-002" },
  });
}

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

/** LEAD-008 · Who may be made the owner. Staff lists change rarely: five minutes is fresh enough. */
export function leadAssigneesQueryOptions() {
  return queryOptions({
    queryKey: leadKeys.assignees(),
    queryFn: ({ signal }) => listAssignees(signal),
    staleTime: 5 * 60_000,
    meta: { dataId: "LEAD-008" },
  });
}

/** LEAD-008 · Partners matching `q`; the previous results stay while the next search loads. */
export function partnerSearchQueryOptions(q: string) {
  return queryOptions({
    queryKey: leadKeys.partners(q),
    queryFn: ({ signal }) => searchPartners(q, signal),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    meta: { dataId: "LEAD-008" },
  });
}
