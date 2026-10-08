import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import {
  getApplication,
  getDocumentLink,
  getStoredCalculation,
  listApplications,
  listChecklist,
  listStageDefs,
  listStageEntries,
} from "./subsidy-applications.api";
import type { ApplicationListParams } from "./subsidy-applications.schemas";

export const applicationKeys = {
  all: ["subsidy-applications"] as const,
  lists: () => [...applicationKeys.all, "list"] as const,
  list: (params: ApplicationListParams) => [...applicationKeys.lists(), params] as const,
  detail: (applicationId: string) => [...applicationKeys.all, "detail", applicationId] as const,
  calculation: (applicationId: string) =>
    [...applicationKeys.detail(applicationId), "calculation"] as const,
  stages: (applicationId: string) => [...applicationKeys.detail(applicationId), "stages"] as const,
  checklist: (applicationId: string) =>
    [...applicationKeys.detail(applicationId), "documents"] as const,
  document: (applicationId: string, documentId: string) =>
    [...applicationKeys.checklist(applicationId), documentId] as const,
  stageDefs: () => [...applicationKeys.all, "stage-defs"] as const,
};

/** The first page has no cursor. */
const FIRST_PAGE: string | null = null;

/** SUBS-005 · A page of applications at a time, newest first. */
export function applicationListQueryOptions(params: ApplicationListParams) {
  return infiniteQueryOptions({
    queryKey: applicationKeys.list(params),
    queryFn: ({ pageParam, signal }) => listApplications({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "SUBS-005" },
  });
}

/** SUBS-006 · One application. */
export function applicationDetailQueryOptions(applicationId: string) {
  return queryOptions({
    queryKey: applicationKeys.detail(applicationId),
    queryFn: ({ signal }) => getApplication(applicationId, signal),
    meta: { dataId: "SUBS-006" },
  });
}

/** SUBS-006 · The calculation as stored at create; it never changes. */
export function storedCalculationQueryOptions(applicationId: string) {
  return queryOptions({
    queryKey: applicationKeys.calculation(applicationId),
    queryFn: ({ signal }) => getStoredCalculation(applicationId, signal),
    staleTime: Infinity,
    meta: { dataId: "SUBS-006" },
  });
}

/** SUBS-006 · The stage history, oldest first. */
export function stageEntriesQueryOptions(applicationId: string) {
  return queryOptions({
    queryKey: applicationKeys.stages(applicationId),
    queryFn: ({ signal }) => listStageEntries(applicationId, signal),
    meta: { dataId: "SUBS-006" },
  });
}

/** SUBS-006 · The stages and their fields. Fixed for now; an admin screen comes later. */
export function stageDefsQueryOptions() {
  return queryOptions({
    queryKey: applicationKeys.stageDefs(),
    queryFn: ({ signal }) => listStageDefs(signal),
    staleTime: 10 * 60_000,
    meta: { dataId: "SUBS-006" },
  });
}

/** SUBS-007 · The document checklist with its files. */
export function checklistQueryOptions(applicationId: string) {
  return queryOptions({
    queryKey: applicationKeys.checklist(applicationId),
    queryFn: ({ signal }) => listChecklist(applicationId, signal),
    meta: { dataId: "SUBS-007" },
  });
}

/** SUBS-007 · A file's ten-minute link, read again before it expires. */
export function documentLinkQueryOptions(applicationId: string, documentId: string) {
  return queryOptions({
    queryKey: applicationKeys.document(applicationId, documentId),
    queryFn: ({ signal }) => getDocumentLink(applicationId, documentId, signal),
    staleTime: 9 * 60_000,
    refetchInterval: 9 * 60_000,
    retry: false,
    meta: { dataId: "SUBS-007" },
  });
}
