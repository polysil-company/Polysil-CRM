import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import type { ApplicationStatus } from "./subsidy-applications.schemas";
import { getAgeing, getStageReport, getSupplyReport } from "./subsidy-reports.api";
import type { AgeingParams } from "./subsidy-reports.schemas";

export const subsidyReportKeys = {
  all: ["subsidy-reports"] as const,
  ageing: (params: AgeingParams) => [...subsidyReportKeys.all, "ageing", params] as const,
  stages: (status: ApplicationStatus) => [...subsidyReportKeys.all, "stages", status] as const,
  supply: (status: ApplicationStatus | null) =>
    [...subsidyReportKeys.all, "supply", status] as const,
};

/** The first page has no cursor. */
const FIRST_PAGE: string | null = null;

/** SUBS-009 · The ageing figures, a page at a time. */
export function ageingQueryOptions(params: AgeingParams) {
  return infiniteQueryOptions({
    queryKey: subsidyReportKeys.ageing(params),
    queryFn: ({ pageParam, signal }) => getAgeing({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "SUBS-009" },
  });
}

/** SUBS-010 · Applications and money in each stage. */
export function stageReportQueryOptions(status: ApplicationStatus) {
  return queryOptions({
    queryKey: subsidyReportKeys.stages(status),
    queryFn: ({ signal }) => getStageReport(status, signal),
    meta: { dataId: "SUBS-010" },
  });
}

/** SUBS-011 · Supplied and not supplied, by district. */
export function supplyReportQueryOptions(status: ApplicationStatus | null) {
  return queryOptions({
    queryKey: subsidyReportKeys.supply(status),
    queryFn: ({ signal }) => getSupplyReport(status, signal),
    meta: { dataId: "SUBS-011" },
  });
}
