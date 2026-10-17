import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import {
  getScheme,
  getStanding,
  getTargetName,
  listEntitlements,
  listSchemes,
  type NamedTargetType,
} from "./schemes.api";
import type { EntitlementListParams, SchemeListParams } from "./schemes.schemas";

export const schemeKeys = {
  all: ["schemes"] as const,
  list: (params: SchemeListParams) => [...schemeKeys.all, "list", params] as const,
  detail: (schemeId: string) => [...schemeKeys.all, "detail", schemeId] as const,
  standing: (schemeId: string, partnerId: string | null) =>
    [...schemeKeys.all, "standing", schemeId, partnerId] as const,
  credits: (params: EntitlementListParams) => [...schemeKeys.all, "credits", params] as const,
  targetName: (type: NamedTargetType, targetId: string) =>
    [...schemeKeys.all, "target-name", type, targetId] as const,
};

/** The first page has no cursor. */
const FIRST_PAGE: string | null = null;

/** SCHM-001 · The schemes, a page at a time. */
export function schemeListQueryOptions(params: SchemeListParams) {
  return infiniteQueryOptions({
    queryKey: schemeKeys.list(params),
    queryFn: ({ pageParam, signal }) => listSchemes({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "SCHM-001" },
  });
}

/** SCHM-001 · One scheme. */
export function schemeDetailQueryOptions(schemeId: string) {
  return queryOptions({
    queryKey: schemeKeys.detail(schemeId),
    queryFn: ({ signal }) => getScheme(schemeId, signal),
    meta: { dataId: "SCHM-001" },
  });
}

/** SCHM-003 · A period scheme's standing for one partner (a partner user: its own). */
export function standingQueryOptions(schemeId: string, partnerId: string | null) {
  return queryOptions({
    queryKey: schemeKeys.standing(schemeId, partnerId),
    queryFn: ({ signal }) => getStanding(schemeId, partnerId, signal),
    meta: { dataId: "SCHM-003" },
  });
}

/** SCHM-004 · Credits, a page at a time. */
export function creditListQueryOptions(params: EntitlementListParams) {
  return infiniteQueryOptions({
    queryKey: schemeKeys.credits(params),
    queryFn: ({ pageParam, signal }) => listEntitlements({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "SCHM-004" },
  });
}

/** SCHM-001 · A target's name from its record; it rarely changes. */
export function targetNameQueryOptions(type: NamedTargetType, targetId: string) {
  return queryOptions({
    queryKey: schemeKeys.targetName(type, targetId),
    queryFn: ({ signal }) => getTargetName(type, targetId, signal),
    staleTime: 10 * 60_000,
    retry: false,
    meta: { dataId: "SCHM-001" },
  });
}
