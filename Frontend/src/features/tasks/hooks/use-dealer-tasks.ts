"use client";

import { useSession } from "@/features/session/hooks/use-session";
import type { TaskListParams, TaskStatus } from "@/features/tasks/api/tasks.schemas";
import { can } from "@/lib/auth/permissions";

/** TASK-009 · A dealer user's own tasks with one status: the dealer's Tasks page lists these. */
export function dealerTaskParams(status: TaskStatus): TaskListParams {
  return { leadId: null, assignedTo: "me", status: [status], type: null, overdue: false };
}

/**
 * TASK-009 · Whether a dealer user has tasks: portal roles hold `tasks` V:own E, and the backend
 * says on `GET /auth/me` whether `tasks_for_dealers` is on (BE-030). Both must hold. Read once
 * per session, so a switch flipped since sign-in can still meet a 403, which the Tasks page
 * explains. Always false for staff.
 */
export function useDealerTasksOn(): boolean {
  const { data: session } = useSession();
  return (
    session !== undefined &&
    session.userType === "partner_user" &&
    session.features.tasksForDealers &&
    can(session.permissions, "tasks", "view")
  );
}
