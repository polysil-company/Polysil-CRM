import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  TASK_PAGE_SIZE,
  plannerDaySchema,
  taskAssigneesSchema,
  taskPageSchema,
  taskResponseSchema,
  teamPageSchema,
  type CancelTaskRequest,
  type CompleteTaskRequest,
  type CreateTaskRequest,
  type PlannerDay,
  type PlannerParams,
  type Task,
  type TaskAssignee,
  type TaskListParams,
  type TaskPage,
  type TeamPage,
} from "./tasks.schemas";

const log = createLogger({ file: "features/tasks/api/tasks.api.ts", dataId: "TASK-001" });

/** Rows a page of the team day asks for; the backend's own page size. */
const TEAM_PAGE_SIZE = 100;

/** TASK-001 · GET /planner — one person's day: due that day, and overdue before it. */
export function getPlannerDay(params: PlannerParams, signal?: AbortSignal): Promise<PlannerDay> {
  return apiRequest({
    dataId: "TASK-001",
    logger: log,
    fn: "getPlannerDay",
    path: "/planner",
    query: { date: params.date, user_id: params.userId ?? undefined },
    schema: plannerDaySchema,
    signal,
  });
}

/** TASK-002 · GET /planner/team — due, done and overdue for each person below the manager. */
export async function getTeamDay(
  params: { date: string; cursor: string | null },
  signal?: AbortSignal,
): Promise<TeamPage> {
  const page = await apiRequest({
    dataId: "TASK-002",
    logger: log,
    fn: "getTeamDay",
    path: "/planner/team",
    query: { date: params.date, cursor: params.cursor, limit: TEAM_PAGE_SIZE },
    schema: teamPageSchema,
    signal,
  });
  logSkipped("getTeamDay", "TASK-002", page.skipped, page.items.length);
  return page;
}

/** TASK-003 · GET /tasks?lead_id= — a lead's tasks and meetings, earliest due first. */
export async function listTasks(
  params: TaskListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<TaskPage> {
  const page = await apiRequest({
    dataId: "TASK-003",
    logger: log,
    fn: "listTasks",
    path: "/tasks",
    query: {
      lead_id: params.leadId,
      cursor: params.cursor,
      limit: TASK_PAGE_SIZE,
      include_total: params.cursor === null,
    },
    schema: taskPageSchema,
    signal,
  });
  logSkipped("listTasks", "TASK-003", page.skipped, page.items.length);
  return page;
}

/** TASK-004 · GET /tasks/assignees — the user first, then the active staff below them. */
export function listTaskAssignees(signal?: AbortSignal): Promise<TaskAssignee[]> {
  return apiRequest({
    dataId: "TASK-004",
    logger: log,
    fn: "listTaskAssignees",
    path: "/tasks/assignees",
    schema: taskAssigneesSchema,
    signal,
  });
}

/** TASK-004 · POST /tasks */
export function createTask({
  body,
  idempotencyKey,
}: {
  body: CreateTaskRequest;
  idempotencyKey: string;
}): Promise<Task> {
  return apiRequest({
    dataId: "TASK-004",
    logger: log,
    fn: "createTask",
    method: "POST",
    path: "/tasks",
    body,
    idempotencyKey,
    schema: taskResponseSchema,
  });
}

/** TASK-005 · POST /tasks/{id}/complete — done, with what happened. */
export function completeTask({
  taskId,
  body,
  idempotencyKey,
}: {
  taskId: string;
  body: CompleteTaskRequest;
  idempotencyKey: string;
}): Promise<Task> {
  return apiRequest({
    dataId: "TASK-005",
    logger: log,
    fn: "completeTask",
    method: "POST",
    path: `/tasks/${encodeURIComponent(taskId)}/complete`,
    body,
    idempotencyKey,
    schema: taskResponseSchema,
  });
}

/** TASK-005 · POST /tasks/{id}/cancel — with a reason. */
export function cancelTask({
  taskId,
  body,
  idempotencyKey,
}: {
  taskId: string;
  body: CancelTaskRequest;
  idempotencyKey: string;
}): Promise<Task> {
  return apiRequest({
    dataId: "TASK-005",
    logger: log,
    fn: "cancelTask",
    method: "POST",
    path: `/tasks/${encodeURIComponent(taskId)}/cancel`,
    body,
    idempotencyKey,
    schema: taskResponseSchema,
  });
}

/** TASK-005 · POST /tasks/{id}/reopen — a done task, within 7 days. */
export function reopenTask({
  taskId,
  idempotencyKey,
}: {
  taskId: string;
  idempotencyKey: string;
}): Promise<Task> {
  return apiRequest({
    dataId: "TASK-005",
    logger: log,
    fn: "reopenTask",
    method: "POST",
    path: `/tasks/${encodeURIComponent(taskId)}/reopen`,
    idempotencyKey,
    schema: taskResponseSchema,
  });
}

/** A backend-side issue: the rest of the list is still shown. */
function logSkipped(
  fn: string,
  dataId: "TASK-002" | "TASK-003",
  skipped: number,
  kept: number,
): void {
  if (skipped > 0) {
    log.warn(fn, `left out ${String(skipped)} row(s) that did not match the contract`, {
      dataId,
      context: { skipped, kept },
    });
  }
}
