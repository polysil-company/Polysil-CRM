"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { leadKeys } from "@/features/leads/api/leads.queries";

import { cancelTask, completeTask, createTask, reopenTask } from "./tasks.api";
import { taskKeys } from "./tasks.queries";
import type {
  CancelTaskRequest,
  CompleteTaskRequest,
  CreateTaskRequest,
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
