import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { getUser, listRoles, listUsers, searchOpenOffices } from "./users.api";
import type { UserListParams } from "./users.schemas";

/**
 * Query keys for people. A change to one person moves them in the list too, so mutations
 * invalidate `userKeys.all`.
 */
export const userKeys = {
  all: ["users"] as const,
  list: (params: Omit<UserListParams, "cursor">) => [...userKeys.all, "list", params] as const,
  detail: (userId: string) => [...userKeys.all, "detail", userId] as const,
  roles: () => [...userKeys.all, "roles"] as const,
  offices: (q: string) => [...userKeys.all, "offices", q] as const,
};

const FIRST_PAGE: string | null = null;

/** ADMN-001 · People, a page at a time. */
export function userListQueryOptions(params: Omit<UserListParams, "cursor">) {
  return infiniteQueryOptions({
    queryKey: userKeys.list(params),
    queryFn: ({ pageParam, signal }) => listUsers({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "ADMN-001" },
  });
}

/** ADMN-002 · One person. */
export function userDetailQueryOptions(userId: string) {
  return queryOptions({
    queryKey: userKeys.detail(userId),
    queryFn: ({ signal }) => getUser(userId, signal),
    meta: { dataId: "ADMN-002" },
  });
}

/** ADMN-003 · The roles; they change only with a release. */
export function roleListQueryOptions() {
  return queryOptions({
    queryKey: userKeys.roles(),
    queryFn: ({ signal }) => listRoles(signal),
    staleTime: 30 * 60_000,
    meta: { dataId: "ADMN-003" },
  });
}

/** ADMN-003 · Open offices matching what was typed. */
export function officeSearchQueryOptions(q: string) {
  return queryOptions({
    queryKey: userKeys.offices(q),
    queryFn: ({ signal }) => searchOpenOffices(q, signal),
    staleTime: 5 * 60_000,
    meta: { dataId: "ADMN-003" },
  });
}
