"use client";

import { useInfiniteQuery } from "@tanstack/react-query";

import { useSession } from "@/features/session/hooks/use-session";
import { taskListQueryOptions } from "@/features/tasks/api/tasks.queries";
import type { TaskListParams, TaskStatus } from "@/features/tasks/api/tasks.schemas";
import { can } from "@/lib/auth/permissions";

/** TASK-009 · A dealer user's own tasks with one status: the dealer's Tasks page lists these. */
export function dealerTaskParams(status: TaskStatus): TaskListParams {
  return { leadId: null, assignedTo: "me", status: [status], type: null, overdue: false };
}

/**
 * TASK-009 · Whether a dealer user has tasks: portal roles hold `tasks` V:own E, but the backend
 * answers 403 on every tasks route while `tasks_for_dealers` is off, and a dealer can't read
 * the setting. So the open tasks are asked for once (the page shares the answer) and the
 * screen shows only when that works. Always false for staff.
 */
export function useDealerTasksOn(): boolean {
  const { data: session } = useSession();
  const eligible =
    session !== undefined &&
    session.userType === "partner_user" &&
    can(session.permissions, "tasks", "view");
  const query = useInfiniteQuery({
    ...taskListQueryOptions(dealerTaskParams("open")),
    enabled: eligible,
    retry: false,
    staleTime: 5 * 60_000,
  });
  return eligible && query.status === "success";
}
