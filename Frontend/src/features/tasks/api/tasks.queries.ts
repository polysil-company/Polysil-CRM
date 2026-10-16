import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import {
  getPlannerDay,
  getTeamDay,
  listLeadMinutes,
  listTaskAssignees,
  listTasks,
} from "./tasks.api";
import type { PlannerParams, TaskListParams } from "./tasks.schemas";

/**
 * Query keys for tasks. A change to one task can move it between a day, a team's counts and
 * a lead's list, so mutations invalidate `taskKeys.all`.
 */
export const taskKeys = {
  all: ["tasks"] as const,
  planner: (params: PlannerParams) => [...taskKeys.all, "planner", params] as const,
  team: (date: string) => [...taskKeys.all, "team", date] as const,
  list: (params: TaskListParams) => [...taskKeys.all, "list", params] as const,
  assignees: () => [...taskKeys.all, "assignees"] as const,
  minutes: (leadId: string) => [...taskKeys.all, "minutes", leadId] as const,
};

const FIRST_PAGE: string | null = null;

/** TASK-001 · One person's day. */
export function plannerDayQueryOptions(params: PlannerParams) {
  return queryOptions({
    queryKey: taskKeys.planner(params),
    queryFn: ({ signal }) => getPlannerDay(params, signal),
    meta: { dataId: "TASK-001" },
  });
}

/** TASK-002 · The team's day, a page of people at a time. */
export function teamDayQueryOptions(date: string) {
  return infiniteQueryOptions({
    queryKey: taskKeys.team(date),
    queryFn: ({ pageParam, signal }) => getTeamDay({ date, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "TASK-002" },
  });
}

/** TASK-003 · Tasks in the user's scope, filtered: a lead's, or the full list. */
export function taskListQueryOptions(params: TaskListParams) {
  return infiniteQueryOptions({
    queryKey: taskKeys.list(params),
    queryFn: ({ pageParam, signal }) => listTasks({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "TASK-003" },
  });
}

/** TASK-004 · Who the user may give a task to; it changes rarely. */
export function taskAssigneesQueryOptions() {
  return queryOptions({
    queryKey: taskKeys.assignees(),
    queryFn: ({ signal }) => listTaskAssignees(signal),
    staleTime: 5 * 60_000,
    meta: { dataId: "TASK-004" },
  });
}

/** TASK-007 · A lead's meeting minutes, newest first. */
export function leadMinutesQueryOptions(leadId: string) {
  return queryOptions({
    queryKey: taskKeys.minutes(leadId),
    queryFn: ({ signal }) => listLeadMinutes(leadId, signal),
    meta: { dataId: "TASK-007" },
  });
}
