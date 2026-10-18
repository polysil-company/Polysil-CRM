import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { trackingKeys } from "./tracking.queries";
import { getTrackingConfig, getVisit, listMyVisits } from "./visits.api";

/** The first page: no cursor yet. */
const FIRST_PAGE: string | null = null;

export const visitKeys = {
  all: [...trackingKeys.all, "visits"] as const,
  config: () => [...trackingKeys.all, "config"] as const,
  mine: (date: string) => [...visitKeys.all, "mine", date] as const,
  detail: (visitId: string) => [...visitKeys.all, "detail", visitId] as const,
};

/** TRK-003 · This person's tracking setup. */
export function trackingConfigQueryOptions() {
  return queryOptions({
    queryKey: visitKeys.config(),
    queryFn: ({ signal }) => getTrackingConfig(signal),
    meta: { dataId: "TRK-003" },
  });
}

/** TRK-005 · My visits of a day, a page at a time. */
export function myVisitsQueryOptions(date: string) {
  return infiniteQueryOptions({
    queryKey: visitKeys.mine(date),
    queryFn: ({ pageParam, signal }) => listMyVisits({ date, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "TRK-005" },
  });
}

/** TRK-005 · One visit. */
export function visitQueryOptions(visitId: string) {
  return queryOptions({
    queryKey: visitKeys.detail(visitId),
    queryFn: ({ signal }) => getVisit(visitId, signal),
    meta: { dataId: "TRK-005" },
  });
}
