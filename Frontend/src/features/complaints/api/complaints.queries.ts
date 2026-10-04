import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import {
  getComplaint,
  getComplaintStats,
  getComplaintTimeline,
  listComplaintAssignees,
  listComplaints,
} from "./complaints.api";
import type { ComplaintListParams } from "./complaints.schemas";

/**
 * Query keys for complaints. A decision moves a complaint between lists, counts and the
 * user's queue, so writes invalidate `complaintKeys.all`.
 */
export const complaintKeys = {
  all: ["complaints"] as const,
  lists: () => [...complaintKeys.all, "list"] as const,
  list: (params: ComplaintListParams) => [...complaintKeys.lists(), params] as const,
  stats: () => [...complaintKeys.all, "stats"] as const,
  detail: (complaintId: string) => [...complaintKeys.all, "detail", complaintId] as const,
  timeline: (complaintId: string) => [...complaintKeys.all, "timeline", complaintId] as const,
  assignees: (complaintId: string) => [...complaintKeys.all, "assignees", complaintId] as const,
};

const FIRST_PAGE: string | null = null;

/** CMPL-001 · A page of complaints at a time. */
export function complaintListQueryOptions(params: ComplaintListParams) {
  return infiniteQueryOptions({
    queryKey: complaintKeys.list(params),
    queryFn: ({ pageParam, signal }) => listComplaints({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "CMPL-001" },
  });
}

/** CMPL-001 · The counts above the list, and whether files can be stored now. */
export function complaintStatsQueryOptions() {
  return queryOptions({
    queryKey: complaintKeys.stats(),
    queryFn: ({ signal }) => getComplaintStats(signal),
    meta: { dataId: "CMPL-001" },
  });
}

/** CMPL-002 · One complaint. */
export function complaintDetailQueryOptions(complaintId: string) {
  return queryOptions({
    queryKey: complaintKeys.detail(complaintId),
    queryFn: ({ signal }) => getComplaint(complaintId, signal),
    meta: { dataId: "CMPL-002" },
  });
}

/** CMPL-002 · Its history, newest first. */
export function complaintTimelineQueryOptions(complaintId: string) {
  return infiniteQueryOptions({
    queryKey: complaintKeys.timeline(complaintId),
    queryFn: ({ pageParam, signal }) =>
      getComplaintTimeline({ complaintId, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "CMPL-002" },
  });
}

/** CMPL-004 · Who may own it, for the check dialog. */
export function complaintAssigneesQueryOptions(complaintId: string) {
  return queryOptions({
    queryKey: complaintKeys.assignees(complaintId),
    queryFn: ({ signal }) => listComplaintAssignees(complaintId, signal),
    meta: { dataId: "CMPL-004" },
  });
}
