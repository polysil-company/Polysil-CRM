import type { LookupItem, LookupList } from "@/features/lookups/api/lookups.schemas";
import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  lookupItemResponseSchema,
  scoringResponseSchema,
  type LookupCreateRequest,
  type LookupUpdateRequest,
  type ScoringItem,
  type ScoringPatchRequest,
} from "./masters.schemas";

const log = createLogger({ file: "features/masters/api/masters.api.ts", dataId: "MSTR-009" });

/** MSTR-009 · POST /lookups/{list}: add a row. */
export function addLookupItem(list: LookupList, body: LookupCreateRequest): Promise<LookupItem> {
  return apiRequest({
    dataId: "MSTR-009",
    logger: log,
    fn: "addLookupItem",
    method: "POST",
    path: `/lookups/${list}`,
    body,
    schema: lookupItemResponseSchema,
  });
}

/** MSTR-009 · PATCH /lookups/{list}/{id}: switch a row on or off. */
export function updateLookupItem(
  list: LookupList,
  itemId: string,
  body: LookupUpdateRequest,
): Promise<LookupItem> {
  return apiRequest({
    dataId: "MSTR-009",
    logger: log,
    fn: "updateLookupItem",
    method: "PATCH",
    path: `/lookups/${list}/${encodeURIComponent(itemId)}`,
    body,
    schema: lookupItemResponseSchema,
  });
}

/** MSTR-010 · GET /lookups/scoring: readable by anyone signed in. */
export function getScoring(signal?: AbortSignal): Promise<ScoringItem[]> {
  return apiRequest({
    dataId: "MSTR-010",
    logger: log,
    fn: "getScoring",
    path: "/lookups/scoring",
    schema: scoringResponseSchema,
    signal,
  });
}

/** MSTR-010 · PATCH /lookups/scoring: `masters.edit` only. Answers every setting. */
export function patchScoring(body: ScoringPatchRequest): Promise<ScoringItem[]> {
  return apiRequest({
    dataId: "MSTR-010",
    logger: log,
    fn: "patchScoring",
    method: "PATCH",
    path: "/lookups/scoring",
    body,
    schema: scoringResponseSchema,
  });
}
