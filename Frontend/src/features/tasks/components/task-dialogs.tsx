"use client";

import type * as React from "react";

import { EditTaskDialog } from "./edit-task-dialog";
import { MinutesDialog } from "./minutes-dialog";
import { TaskActionDialog, type PendingTaskAction } from "./task-action-dialog";

export interface TaskDialogsProps {
  /** What was chosen on a task's row; null when nothing is open. */
  pending: PendingTaskAction | null;
  meId: string | null;
  onClose: () => void;
}

/**
 * The dialogs a task's row opens, in one place: done or cancel (TASK-005), edit or reassign
 * (TASK-006), and minutes for a meeting on a lead (TASK-007).
 */
export function TaskDialogs({ pending, meId, onClose }: TaskDialogsProps): React.JSX.Element {
  const doneOrCancel =
    pending !== null && (pending.kind === "complete" || pending.kind === "cancel")
      ? { task: pending.task, kind: pending.kind }
      : null;
  const lead = pending?.kind === "minutes" ? pending.task.lead : null;

  return (
    <>
      <TaskActionDialog pending={doneOrCancel} onClose={onClose} />
      <EditTaskDialog
        task={pending?.kind === "edit" ? pending.task : null}
        meId={meId}
        onClose={onClose}
      />
      <MinutesDialog
        subject={
          pending === null || lead === null || lead.hidden
            ? null
            : {
                leadId: lead.id,
                leadName: lead.farmerName ?? lead.inquiryNo ?? "this lead",
                meeting: pending.task,
              }
        }
        meId={meId}
        onClose={onClose}
      />
    </>
  );
}
