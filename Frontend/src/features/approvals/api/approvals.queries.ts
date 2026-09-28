import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { listPendingApprovals } from "./approvals.api";
import type { QueueParams } from "./approvals.schemas";

/** How often the inbox and its badge look for new requests. */
export const APPROVALS_POLL_MS = 60_000;

/**
 * Query keys for approvals. Invalidate `approvalKeys.all` after a decision: the inbox and
 * the badge both change.
 */
export const approvalKeys = {
  all: ["approvals"] as const,
  queue: (params: QueueParams) => [...approvalKeys.all, "queue", params] as const,
  count: () => [...approvalKeys.all, "count"] as const,
};

const FIRST_PAGE: string | null = null;

/** APPR-001 · The inbox, a page at a time, re-read every minute. */
export function approvalQueueQueryOptions(params: QueueParams) {
  return infiniteQueryOptions({
    queryKey: approvalKeys.queue(params),
    queryFn: ({ pageParam, signal }) =>
      listPendingApprovals({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    refetchInterval: APPROVALS_POLL_MS,
    meta: { dataId: "APPR-001" },
  });
}

/** APPR-001 · How many requests wait on the user, for the sidebar badge. */
export function approvalCountQueryOptions() {
  return queryOptions({
    queryKey: approvalKeys.count(),
    queryFn: async ({ signal }) => {
      const page = await listPendingApprovals(
        { includeBelow: false, cursor: null, limit: 1 },
        signal,
      );
      return { total: page.total ?? page.items.length, capped: page.totalCapped };
    },
    refetchInterval: APPROVALS_POLL_MS,
    meta: { dataId: "APPR-001" },
  });
}
