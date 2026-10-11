import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  TASK_PAGE_SIZE,
  minutesListSchema,
  minutesResponseSchema,
  plannerDaySchema,
  taskAssigneesSchema,
  taskPageSchema,
  taskResponseSchema,
  teamPageSchema,
  type CancelTaskRequest,
  type CompleteTaskRequest,
  type CreateMinutesRequest,
  type CreateTaskRequest,
  type Minutes,
  type PatchTaskRequest,
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

/** The filters GET /tasks and GET /tasks/export share, as query parameters. */
function taskFilterQuery(
  params: TaskListParams,
): Record<string, string | boolean | string[] | undefined> {
  return {
    lead_id: params.leadId ?? undefined,
    assigned_to: params.assignedTo ?? undefined,
    status: params.status.length === 0 ? undefined : [...params.status],
    task_type: params.type ?? undefined,
    overdue: params.overdue ? true : undefined,
  };
}

/** TASK-003 · GET /tasks — tasks in the user's scope, earliest due first, filtered. */
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
      ...taskFilterQuery(params),
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

/**
 * TASK-008 · GET /tasks/export — the list as an Excel file, with the same filters: every
 * page, nothing outside the user's scope. More than 5,000 rows is `422 export_too_large`.
 */
export function exportTasks(params: TaskListParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "TASK-008",
    logger: log,
    fn: "exportTasks",
    path: "/tasks/export",
    query: taskFilterQuery(params),
  });
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

/** TASK-006 · PATCH /tasks/{id} — an open task's title, due time or notes, or who does it. */
export function patchTask({
  taskId,
  body,
  idempotencyKey,
}: {
  taskId: string;
  body: PatchTaskRequest;
  idempotencyKey: string;
}): Promise<Task> {
  return apiRequest({
    dataId: "TASK-006",
    logger: log,
    fn: "patchTask",
    method: "PATCH",
    path: `/tasks/${encodeURIComponent(taskId)}`,
    body,
    idempotencyKey,
    schema: taskResponseSchema,
  });
}

/** TASK-007 · GET /minutes?lead_id= — a lead's meeting minutes, newest first. */
export function listLeadMinutes(leadId: string, signal?: AbortSignal): Promise<Minutes[]> {
  return apiRequest({
    dataId: "TASK-007",
    logger: log,
    fn: "listLeadMinutes",
    path: "/minutes",
    query: { lead_id: leadId },
    schema: minutesListSchema,
    signal,
  });
}

/**
 * TASK-007 · POST /minutes — the minutes and a task per action item, in one save. One bad
 * action item refuses the whole save, with `fields.action_items[i]…`.
 */
export function createMinutes({
  body,
  idempotencyKey,
}: {
  body: CreateMinutesRequest;
  idempotencyKey: string;
}): Promise<Minutes> {
  return apiRequest({
    dataId: "TASK-007",
    logger: log,
    fn: "createMinutes",
    method: "POST",
    path: "/minutes",
    body,
    idempotencyKey,
    schema: minutesResponseSchema,
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
