import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { listLookup, searchTerritories } from "./lookups.api";
import type { LookupList, TerritorySearchParams } from "./lookups.schemas";

/** Administrators change these lists rarely; ten minutes is fresh enough. */
const LOOKUP_STALE_TIME_MS = 10 * 60_000;

export const lookupKeys = {
  all: ["lookups"] as const,
  list: (list: LookupList) => [...lookupKeys.all, list] as const,
  territories: (params: TerritorySearchParams) =>
    [...lookupKeys.all, "territories", params] as const,
};

/** One request per list, shared by every cell, filter and form that names a code. */
export function lookupListQueryOptions(list: LookupList) {
  return queryOptions({
    queryKey: lookupKeys.list(list),
    queryFn: ({ signal }) => listLookup(list, signal),
    staleTime: LOOKUP_STALE_TIME_MS,
    meta: { dataId: "MSTR-002" },
  });
}

/** Keeps the previous results on screen while the next search loads — no flicker as people type. */
export function territorySearchQueryOptions(params: TerritorySearchParams) {
  return queryOptions({
    queryKey: lookupKeys.territories(params),
    queryFn: ({ signal }) => searchTerritories(params, signal),
    staleTime: LOOKUP_STALE_TIME_MS,
    placeholderData: keepPreviousData,
    meta: { dataId: "MSTR-002" },
  });
}
