import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import {
  getAttachmentLink,
  getComplaint,
  getComplaintStats,
  getComplaintTimeline,
  listComplaintAssignees,
  listComplaints,
  listSlaPolicies,
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
  attachment: (complaintId: string, attachmentId: string) =>
    [...complaintKeys.all, "attachment", complaintId, attachmentId] as const,
  slaPolicies: () => [...complaintKeys.all, "sla-policies"] as const,
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

/**
 * CMPL-006 · A file's ten-minute link. Re-read after nine minutes, so a thumbnail left open
 * never points at an expired link.
 */
export function attachmentLinkQueryOptions(complaintId: string, attachmentId: string) {
  return queryOptions({
    queryKey: complaintKeys.attachment(complaintId, attachmentId),
    queryFn: ({ signal }) => getAttachmentLink(complaintId, attachmentId, signal),
    staleTime: 9 * 60_000,
    refetchInterval: 9 * 60_000,
    meta: { dataId: "CMPL-006" },
  });
}

/** CMPL-008 · The response and resolution targets. */
export function slaPoliciesQueryOptions() {
  return queryOptions({
    queryKey: complaintKeys.slaPolicies(),
    queryFn: ({ signal }) => listSlaPolicies(signal),
    meta: { dataId: "CMPL-008" },
  });
}
