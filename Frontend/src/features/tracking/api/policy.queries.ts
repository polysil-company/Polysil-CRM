import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { getTrackingPolicy, listViewLog } from "./policy.api";
import { trackingKeys } from "./tracking.queries";

/** The first page: no cursor yet. */
const FIRST_PAGE: string | null = null;

export const policyKeys = {
  policy: () => [...trackingKeys.all, "policy"] as const,
  viewLog: (subjectUserId: string | null) =>
    [...trackingKeys.all, "view-log", subjectUserId] as const,
};

/** TRK-006 · The policy in force. */
export function trackingPolicyQueryOptions() {
  return queryOptions({
    queryKey: policyKeys.policy(),
    queryFn: ({ signal }) => getTrackingPolicy(signal),
    meta: { dataId: "TRK-006" },
  });
}

/** TRK-007 · The view log, optionally for one person, a page at a time. */
export function viewLogQueryOptions(subjectUserId: string | null) {
  return infiniteQueryOptions({
    queryKey: policyKeys.viewLog(subjectUserId),
    queryFn: ({ pageParam, signal }) => listViewLog({ subjectUserId, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "TRK-007" },
  });
}
