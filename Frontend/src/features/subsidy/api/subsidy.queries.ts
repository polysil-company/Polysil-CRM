import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import {
  calculateSubsidy,
  getSubsidyConfig,
  listSubsidyCategories,
  listSubsidyCrops,
} from "./subsidy.api";
import type { CalculateRequest, SystemType } from "./subsidy.schemas";

/** The masters change when the scheme changes them, not within a working session. */
const MASTERS_STALE_MS = 10 * 60_000;

export const subsidyKeys = {
  all: ["subsidy"] as const,
  config: (scheme: string | null) => [...subsidyKeys.all, "config", scheme] as const,
  crops: (scheme: string | null) => [...subsidyKeys.all, "crops", scheme] as const,
  categories: (systemType: SystemType, scheme: string | null) =>
    [...subsidyKeys.all, "categories", systemType, scheme] as const,
  calculation: (request: CalculateRequest) => [...subsidyKeys.all, "calculation", request] as const,
};

/**
 * SUBS-003 · What each system accepts, for a scheme (null: the backend's default, GGRC). Read
 * once when the calculator opens.
 */
export function subsidyConfigQueryOptions(scheme: string | null = null) {
  return queryOptions({
    queryKey: subsidyKeys.config(scheme),
    queryFn: ({ signal }) => getSubsidyConfig(scheme, signal),
    staleTime: MASTERS_STALE_MS,
    meta: { dataId: "SUBS-003" },
  });
}

/** SUBS-003 · The crop picker's rows. */
export function subsidyCropsQueryOptions(scheme: string | null = null) {
  return queryOptions({
    queryKey: subsidyKeys.crops(scheme),
    queryFn: ({ signal }) => listSubsidyCrops(scheme, signal),
    staleTime: MASTERS_STALE_MS,
    meta: { dataId: "SUBS-003" },
  });
}

/** SUBS-003 · A system's categories, shown before anything is calculated. */
export function subsidyCategoriesQueryOptions(
  systemType: SystemType,
  scheme: string | null = null,
) {
  return queryOptions({
    queryKey: subsidyKeys.categories(systemType, scheme),
    queryFn: ({ signal }) => listSubsidyCategories(systemType, scheme, signal),
    staleTime: MASTERS_STALE_MS,
    meta: { dataId: "SUBS-003" },
  });
}

/**
 * SUBS-002 · The breakdown for one set of inputs. The previous figures stay on screen while the
 * next arrive; a refusal (a 422 naming a field) is never retried.
 */
export function subsidyCalculationQueryOptions(request: CalculateRequest) {
  return queryOptions({
    queryKey: subsidyKeys.calculation(request),
    queryFn: ({ signal }) => calculateSubsidy(request, signal),
    placeholderData: keepPreviousData,
    staleTime: 60_000,
    retry: false,
    meta: { dataId: "SUBS-002" },
  });
}
