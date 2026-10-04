"use client";

import { MoreHorizontalIcon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Icon } from "@/components/ui/icon";
import { useReopenTask } from "@/features/tasks/api/tasks.mutations";
import type { Task } from "@/features/tasks/api/tasks.schemas";
import {
  TASK_TYPE_ICONS,
  TASK_TYPE_LABELS,
  taskRefusal,
  taskSubjectLabel,
} from "@/features/tasks/lib/task-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatDateTime, formatTime } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import type { PendingTaskAction } from "./task-action-dialog";

const log = createLogger({ file: "features/tasks/components/task-row.tsx", dataId: "TASK-005" });

export interface TaskRowProps {
  task: Task;
  /** The signed-in user's id: decides who may cancel or reopen. */
  meId: string | null;
  /** May change tasks at all (`tasks.edit`). */
  canEdit: boolean;
  /** "time" in a day's list; "date" where tasks from several days mix. */
  when: "time" | "date";
  /** Name the person it is for — on a lead, or a manager's view of someone's day. */
  showAssignee?: boolean;
  /** Not linked to the lead it is about, when already on that lead's page. */
  hideSubject?: boolean;
  onAction: (action: PendingTaskAction) => void;
}

/**
 * TASK-001 · One task: what it is, when, what it is about, and who gave it; done tasks say
 * what happened, cancelled ones why. Open tasks are marked done in place. The menu edits or
 * reassigns an open task, records minutes for a meeting on a lead, cancels (unless someone
 * else gave it to you: only they can) or reopens a done one.
 */
export function TaskRow({
  task,
  meId,
  canEdit,
  when,
  showAssignee = false,
  hideSubject = false,
  onAction,
}: TaskRowProps): React.JSX.Element {
  const subject = hideSubject ? null : taskSubjectLabel(task);
  const open = task.status === "open";
  const givenByOther =
    task.assignedBy !== null && task.assignedBy.id !== task.assignedTo?.id ? task.assignedBy : null;
  const canCancel = canEdit && open && !(task.assignedTo?.id === meId && givenByOther !== null);
  const canChange = canEdit && open;
  const canRecordMinutes =
    canEdit &&
    task.type === "meeting" &&
    task.status !== "cancelled" &&
    task.lead !== null &&
    !task.lead.hidden;
  const canReopen =
    canEdit &&
    task.status === "done" &&
    meId !== null &&
    (task.assignedTo?.id === meId || task.assignedBy?.id === meId);

  return (
    <li
      aria-label={`${TASK_TYPE_LABELS[task.type]}: ${task.title}`}
      className={cn(
        "flex gap-3 rounded-xl border border-border bg-card p-3 sm:p-4",
        task.overdue && "border-danger/40",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full",
          task.status === "done"
            ? "bg-success-soft text-success"
            : task.overdue
              ? "bg-danger-soft text-danger"
              : "bg-muted text-muted-foreground",
        )}
      >
        <Icon icon={TASK_TYPE_ICONS[task.type]} size="sm" />
      </span>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p
            className={cn(
              "text-sm font-medium text-pretty text-foreground",
              task.status === "cancelled" && "text-muted-foreground line-through",
            )}
          >
            {task.title}
          </p>
          {task.overdue ? <Badge variant="danger">Overdue</Badge> : null}
          {task.status === "done" ? <Badge variant="success">Done</Badge> : null}
          {task.status === "cancelled" ? <Badge variant="outline">Cancelled</Badge> : null}
        </div>

        <p className="flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
          <time dateTime={task.dueAt} className="font-medium text-foreground tabular-nums">
            {when === "time" ? formatTime(task.dueAt) : formatDateTime(task.dueAt)}
          </time>
          <span aria-hidden="true">·</span>
          <span>{TASK_TYPE_LABELS[task.type]}</span>
          {task.meetingType === null ? null : (
            <>
              <span aria-hidden="true">·</span>
              <span>{task.meetingType.name}</span>
            </>
          )}
          {subject === null ? null : (
            <>
              <span aria-hidden="true">·</span>
              <TaskSubject task={task} label={subject} />
            </>
          )}
        </p>

        {showAssignee && task.assignedTo !== null ? (
          <p className="text-xs text-muted-foreground">For {task.assignedTo.name}</p>
        ) : null}
        {givenByOther === null ? null : (
          <p className="text-xs text-muted-foreground">
            Given by {givenByOther.id === meId ? "you" : givenByOther.name}
          </p>
        )}
        {task.minutesId === null ? null : (
          <p className="text-xs text-muted-foreground">From meeting minutes</p>
        )}
        {task.notes === null || !open ? null : (
          <p className="line-clamp-2 text-sm text-pretty text-muted-foreground">{task.notes}</p>
        )}
        {task.status === "done" && task.outcome !== null ? (
          <p className="text-sm text-pretty text-foreground">
            <span className="sr-only">What happened: </span>
            {task.outcome}
            {task.giftShown === true ? (
              <span className="text-muted-foreground"> · Gift shown</span>
            ) : null}
          </p>
        ) : null}
        {task.status === "cancelled" && task.cancelReason !== null ? (
          <p className="text-sm text-pretty text-muted-foreground">
            <span className="sr-only">Why it was cancelled: </span>
            {task.cancelReason}
          </p>
        ) : null}
      </div>

      {canEdit ? (
        <div className="flex shrink-0 items-start gap-1">
          {open ? (
            <Button
              variant="outline"
              size="sm"
              aria-label={`Mark done: ${task.title}`}
              onClick={() => {
                onAction({ task, kind: "complete" });
              }}
            >
              Done
            </Button>
          ) : null}
          {canCancel || canReopen || canChange || canRecordMinutes ? (
            <TaskMenu
              task={task}
              canEdit={canChange}
              canRecordMinutes={canRecordMinutes}
              canCancel={canCancel}
              canReopen={canReopen}
              onAction={onAction}
            />
          ) : (
            // Keeps Done in line with the rows that have a menu.
            <span aria-hidden="true" className="size-control-sm" />
          )}
        </div>
      ) : null}
    </li>
  );
}

/** The lead or order the task is about, as a link; a dealer, or anything hidden, as text. */
function TaskSubject({ task, label }: { task: Task; label: string }): React.JSX.Element {
  if (task.lead !== null && !task.lead.hidden) {
    return (
      <Link
        href={`/leads/${task.lead.id}`}
        className="font-medium text-foreground underline-offset-2 hover:underline"
      >
        {label}
      </Link>
    );
  }
  if (task.salesOrder !== null && !task.salesOrder.hidden) {
    return (
      <Link
        href={`/sales-orders/${task.salesOrder.id}`}
        className="font-medium text-foreground underline-offset-2 hover:underline"
      >
        {label}
      </Link>
    );
  }
  return <span>{label}</span>;
}

function TaskMenu({
  task,
  canEdit,
  canRecordMinutes,
  canCancel,
  canReopen,
  onAction,
}: {
  task: Task;
  canEdit: boolean;
  canRecordMinutes: boolean;
  canCancel: boolean;
  canReopen: boolean;
  onAction: (action: PendingTaskAction) => void;
}): React.JSX.Element {
  const reopen = useReopenTask();
  const idempotency = useIdempotencyKey();
  const run = useAsyncAction({
    action: () =>
      reopen.mutateAsync({
        taskId: task.id,
        idempotencyKey: idempotency.keyFor({ reopen: task.id }),
      }),
    logger: log,
    fn: "handleReopenTask",
    dataId: "TASK-005",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Task reopened", { description: task.title });
    },
    onError: (error) => {
      const view = taskRefusal(error);
      toast.error(view.title, { description: view.message });
    },
  });

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`More for ${task.title}`}
            disabled={run.isBusy}
          />
        }
      >
        <Icon icon={MoreHorizontalIcon} />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {canEdit ? (
          <DropdownMenuItem
            onClick={() => {
              onAction({ task, kind: "edit" });
            }}
          >
            Edit or reassign
          </DropdownMenuItem>
        ) : null}
        {canRecordMinutes ? (
          <DropdownMenuItem
            onClick={() => {
              onAction({ task, kind: "minutes" });
            }}
          >
            Record minutes
          </DropdownMenuItem>
        ) : null}
        {canReopen ? (
          <DropdownMenuItem
            onClick={() => {
              void run.run();
            }}
          >
            Reopen
          </DropdownMenuItem>
        ) : null}
        {canCancel ? (
          <DropdownMenuItem
            variant="destructive"
            onClick={() => {
              onAction({ task, kind: "cancel" });
            }}
          >
            Cancel task
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
