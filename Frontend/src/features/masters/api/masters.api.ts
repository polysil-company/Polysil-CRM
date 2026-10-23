import type { LookupItem, LookupList } from "@/features/lookups/api/lookups.schemas";
import { apiRequest } from "@/lib/api/client";
import type { CursorPage } from "@/lib/api/pagination";
import { createLogger } from "@/lib/logger";

import {
  lookupItemResponseSchema,
  officeListSchema,
  officeResponseSchema,
  scoringResponseSchema,
  type LookupCreateRequest,
  type LookupUpdateRequest,
  type Office,
  type OfficeCreateRequest,
  type OfficeListParams,
  type OfficePatchRequest,
  type ScoringItem,
  type ScoringPatchRequest,
  territoryListSchema,
  territoryResponseSchema,
  type Territory,
  type TerritoryCreateRequest,
  type TerritoryListParams,
  type TerritoryPatchRequest,
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

/** Offices per page. */
export const OFFICE_PAGE_SIZE = 50;

function officePath(officeId: string): `/org-units/${string}` {
  return `/org-units/${encodeURIComponent(officeId)}`;
}

/** MSTR-011 · GET /org-units: the office tree, newest first, by name and open or closed. */
export function listOffices(
  params: OfficeListParams,
  signal?: AbortSignal,
): Promise<CursorPage<Office>> {
  return apiRequest({
    dataId: "MSTR-011",
    logger: log,
    fn: "listOffices",
    path: "/org-units",
    query: {
      q: params.q.trim() === "" ? undefined : params.q.trim(),
      is_open: params.state === "all" ? undefined : params.state === "open",
      limit: OFFICE_PAGE_SIZE,
      cursor: params.cursor ?? undefined,
    },
    schema: officeListSchema,
    signal,
  });
}

/** MSTR-011 · POST /org-units: under an open office, or as a root. */
export function createOffice(body: OfficeCreateRequest): Promise<Office> {
  return apiRequest({
    dataId: "MSTR-011",
    logger: log,
    fn: "createOffice",
    method: "POST",
    path: "/org-units",
    body,
    schema: officeResponseSchema,
  });
}

/** MSTR-011 · PATCH /org-units/{id}: only what changes. */
export function patchOffice(officeId: string, body: OfficePatchRequest): Promise<Office> {
  return apiRequest({
    dataId: "MSTR-011",
    logger: log,
    fn: "patchOffice",
    method: "PATCH",
    path: officePath(officeId),
    body,
    schema: officeResponseSchema,
  });
}

/** MSTR-011 · Close (refused while people are anchored on it) or reopen an office. */
export function setOfficeOpen(officeId: string, open: boolean): Promise<Office> {
  return apiRequest({
    dataId: "MSTR-011",
    logger: log,
    fn: open ? "reopenOffice" : "closeOffice",
    method: "POST",
    path: `${officePath(officeId)}/${open ? "reopen" : "close"}`,
    schema: officeResponseSchema,
  });
}

/** Territories per page. */
export const TERRITORY_PAGE_SIZE = 50;

/** MSTR-012 · GET /territories: the tree for administration, newest first, filtered. */
export function listTerritories(
  params: TerritoryListParams,
  signal?: AbortSignal,
): Promise<CursorPage<Territory>> {
  return apiRequest({
    dataId: "MSTR-012",
    logger: log,
    fn: "listTerritories",
    path: "/territories",
    query: {
      level: params.level ?? undefined,
      parent_id: params.parentId ?? undefined,
      q: params.q.trim() === "" ? undefined : params.q.trim(),
      limit: TERRITORY_PAGE_SIZE,
      cursor: params.cursor ?? undefined,
    },
    schema: territoryListSchema,
    signal,
  });
}

/** MSTR-012 · POST /territories: names unique among siblings, codes unique per level. */
export function createTerritory(body: TerritoryCreateRequest): Promise<Territory> {
  return apiRequest({
    dataId: "MSTR-012",
    logger: log,
    fn: "createTerritory",
    method: "POST",
    path: "/territories",
    body,
    schema: territoryResponseSchema,
  });
}

/** MSTR-012 · PATCH /territories/{id}: rename or set the code. */
export function patchTerritory(
  territoryId: string,
  body: TerritoryPatchRequest,
): Promise<Territory> {
  return apiRequest({
    dataId: "MSTR-012",
    logger: log,
    fn: "patchTerritory",
    method: "PATCH",
    path: `/territories/${encodeURIComponent(territoryId)}`,
    body,
    schema: territoryResponseSchema,
  });
}
