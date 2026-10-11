import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  lookupListResponseSchema,
  territoryListResponseSchema,
  type LookupItem,
  type LookupList,
  type TerritoryOption,
  type TerritorySearchParams,
} from "./lookups.schemas";

const log = createLogger({ file: "features/lookups/api/lookups.api.ts", dataId: "MSTR-002" });

/** MSTR-002 · GET /lookups/{list} — every row, inactive ones included. */
export function listLookup(list: LookupList, signal?: AbortSignal): Promise<LookupItem[]> {
  return apiRequest({
    dataId: "MSTR-002",
    logger: log,
    fn: "listLookup",
    path: `/lookups/${list}`,
    schema: lookupListResponseSchema,
    signal,
  });
}

/** MSTR-002 · GET /lookups/territories */
export function searchTerritories(
  params: TerritorySearchParams,
  signal?: AbortSignal,
): Promise<TerritoryOption[]> {
  return apiRequest({
    dataId: "MSTR-002",
    logger: log,
    fn: "searchTerritories",
    path: "/lookups/territories",
    query: {
      q: params.q,
      level: params.level,
      levels: params.levels === null ? null : params.levels.join(","),
      limit: params.limit,
    },
    schema: territoryListResponseSchema,
    signal,
  });
}
