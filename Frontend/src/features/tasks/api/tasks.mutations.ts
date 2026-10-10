"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { leadKeys } from "@/features/leads/api/leads.queries";

import {
  cancelTask,
  completeTask,
  createMinutes,
  createTask,
  patchTask,
  reopenTask,
} from "./tasks.api";
import { taskKeys } from "./tasks.queries";
import type {
  CancelTaskRequest,
  CompleteTaskRequest,
  CreateMinutesRequest,
  CreateTaskRequest,
  Minutes,
  PatchTaskRequest,
  Task,
} from "./tasks.schemas";

/** Every task view, and the history of the lead the task is about. */
function useRefreshAfter(): (task: Task) => void {
  const queryClient = useQueryClient();
  return (task) => {
    void queryClient.invalidateQueries({ queryKey: taskKeys.all });
    if (task.lead !== null) {
      void queryClient.invalidateQueries({ queryKey: leadKeys.timeline(task.lead.id) });
    }
  };
}

/** TASK-004 · Create a task. */
export function useCreateTask(): UseMutationResult<
  Task,
  Error,
  { body: CreateTaskRequest; idempotencyKey: string }
> {
  const refresh = useRefreshAfter();
  return useMutation({
    mutationKey: [...taskKeys.all, "create"],
    mutationFn: createTask,
    meta: { dataId: "TASK-004" },
    onSuccess: refresh,
  });
}

/** TASK-005 · Mark a task done. */
export function useCompleteTask(): UseMutationResult<
  Task,
  Error,
  { taskId: string; body: CompleteTaskRequest; idempotencyKey: string }
> {
  const refresh = useRefreshAfter();
  return useMutation({
    mutationKey: [...taskKeys.all, "complete"],
    mutationFn: completeTask,
    meta: { dataId: "TASK-005" },
    onSuccess: refresh,
  });
}

/** TASK-005 · Cancel a task, with a reason. */
export function useCancelTask(): UseMutationResult<
  Task,
  Error,
  { taskId: string; body: CancelTaskRequest; idempotencyKey: string }
> {
  const refresh = useRefreshAfter();
  return useMutation({
    mutationKey: [...taskKeys.all, "cancel"],
    mutationFn: cancelTask,
    meta: { dataId: "TASK-005" },
    onSuccess: refresh,
  });
}

/** TASK-005 · Reopen a done task. */
export function useReopenTask(): UseMutationResult<
  Task,
  Error,
  { taskId: string; idempotencyKey: string }
> {
  const refresh = useRefreshAfter();
  return useMutation({
    mutationKey: [...taskKeys.all, "reopen"],
    mutationFn: reopenTask,
    meta: { dataId: "TASK-005" },
    onSuccess: refresh,
  });
}

/** TASK-006 · Change an open task, or give it to someone else. */
export function usePatchTask(): UseMutationResult<
  Task,
  Error,
  { taskId: string; body: PatchTaskRequest; idempotencyKey: string }
> {
  const refresh = useRefreshAfter();
  return useMutation({
    mutationKey: [...taskKeys.all, "patch"],
    mutationFn: patchTask,
    meta: { dataId: "TASK-006" },
    onSuccess: refresh,
  });
}

/**
 * TASK-007 · Record a meeting's minutes. Its action items become tasks, and the meeting it
 * records is marked done: every task view and the lead's history refresh.
 */
export function useCreateMinutes(): UseMutationResult<
  Minutes,
  Error,
  { leadId: string; body: CreateMinutesRequest; idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...taskKeys.all, "minutes", "create"],
    mutationFn: ({ body, idempotencyKey }) => createMinutes({ body, idempotencyKey }),
    meta: { dataId: "TASK-007" },
    onSuccess: (_minutes, { leadId }) => {
      void queryClient.invalidateQueries({ queryKey: taskKeys.all });
      void queryClient.invalidateQueries({ queryKey: leadKeys.timeline(leadId) });
    },
  });
}
