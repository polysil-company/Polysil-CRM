"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCancelTask, useCompleteTask } from "@/features/tasks/api/tasks.mutations";
import { TASK_TEXT_MAX, type Task } from "@/features/tasks/api/tasks.schemas";
import { taskRefusal, taskSubjectLabel } from "@/features/tasks/lib/task-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatDateTime } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/tasks/components/task-action-dialog.tsx",
  dataId: "TASK-005",
});

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

export type TaskActionKind = "complete" | "cancel";

/** What was chosen on a task's row: a dialog to open. See `TaskDialogs`. */
export interface PendingTaskAction {
  readonly task: Task;
  readonly kind: TaskActionKind | "edit" | "minutes";
}

/** Done or cancel: the two this dialog handles. */
interface PendingDoneOrCancel {
  readonly task: Task;
  readonly kind: TaskActionKind;
}

interface ActionForm {
  text: string;
  giftShown: boolean;
}

function actionFormSchema(kind: TaskActionKind): z.ZodType<ActionForm, ActionForm> {
  return z.object({
    text: z
      .string()
      .trim()
      .min(1, kind === "complete" ? "Say what happened." : "Say why it is cancelled.")
      .max(TASK_TEXT_MAX, `Keep it under ${String(TASK_TEXT_MAX)} characters.`),
    giftShown: z.boolean(),
  });
}

export interface TaskActionDialogProps {
  /** The task and what to do with it; null when closed. */
  pending: PendingDoneOrCancel | null;
  onClose: () => void;
}

/**
 * TASK-005 · Mark a task done, with what happened (and, for a meeting, whether the gift was
 * shown), or cancel it with a reason. A task someone else moved on meanwhile closes the
 * dialog and refreshes the list.
 */
export function TaskActionDialog({ pending, onClose }: TaskActionDialogProps): React.JSX.Element {
  return (
    <Dialog
      open={pending !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent size="sm">
        {pending === null ? null : (
          <ActionForm key={`${pending.task.id}-${pending.kind}`} {...pending} onClose={onClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ActionForm({
  task,
  kind,
  onClose,
}: PendingDoneOrCancel & { onClose: () => void }): React.JSX.Element {
  const complete = useCompleteTask();
  const cancel = useCancelTask();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const form = useForm<ActionForm>({
    resolver: zodResolver(actionFormSchema(kind)),
    defaultValues: { text: "", giftShown: false },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    return () => {
      window.clearTimeout(timer.current);
    };
  }, []);

  const completing = kind === "complete";
  const meeting = task.type === "meeting";
  const subject = taskSubjectLabel(task);

  const submit = useAsyncAction({
    action: (values: ActionForm) => {
      if (completing) {
        const body = { outcome: values.text.trim(), gift_shown: meeting ? values.giftShown : null };
        return complete.mutateAsync({
          taskId: task.id,
          body,
          idempotencyKey: idempotency.keyFor({ task: task.id, ...body }),
        });
      }
      const body = { reason: values.text.trim() };
      return cancel.mutateAsync({
        taskId: task.id,
        body,
        idempotencyKey: idempotency.keyFor({ task: task.id, ...body }),
      });
    },
    logger: log,
    fn: completing ? "handleCompleteTask" : "handleCancelTask",
    dataId: "TASK-005",
    onSuccess: () => {
      idempotency.reset();
      toast.success(completing ? "Marked done" : "Task cancelled", { description: task.title });
      timer.current = window.setTimeout(onClose, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      const view = taskRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      const fieldError = view.fields?.outcome ?? view.fields?.reason;
      if (fieldError !== undefined) {
        form.setError("text", { type: "server", message: fieldError });
        return;
      }
      setRefusal({ title: view.title, message: view.message });
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => submit.run(values))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>{completing ? "Mark as done" : "Cancel this task?"}</DialogTitle>
        <DialogDescription>
          {task.title} · due {formatDateTime(task.dueAt)}
          {subject === null ? "" : ` · ${subject}`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={errors.text ? true : undefined}>
          <FieldLabel htmlFor="task-action-text">
            {completing ? "What happened" : "Reason"}
          </FieldLabel>
          <Textarea
            id="task-action-text"
            rows={3}
            placeholder={
              completing
                ? "Spoke to him; he wants the revised quotation by Friday."
                : "The farmer went with another company."
            }
            aria-invalid={errors.text ? true : undefined}
            aria-describedby={errors.text ? "task-action-text-error" : "task-action-text-hint"}
            {...form.register("text")}
          />
          {errors.text ? null : (
            <FieldDescription id="task-action-text-hint">
              {completing
                ? "Kept with the task, and on the lead's history."
                : "Whoever gave the task reads it."}
            </FieldDescription>
          )}
          <FieldError id="task-action-text-error">{errors.text?.message}</FieldError>
        </Field>
        {completing && meeting ? (
          <Controller
            control={form.control}
            name="giftShown"
            render={({ field }) => (
              <div className="flex items-center gap-2">
                <Checkbox
                  id="task-action-gift"
                  checked={field.value}
                  onCheckedChange={(checked) => {
                    field.onChange(checked);
                  }}
                />
                <Label htmlFor="task-action-gift" className="text-sm">
                  The gift was shown at this meeting
                </Label>
              </div>
            )}
          />
        ) : null}
        {refusal === null ? null : (
          <div
            role="alert"
            className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
          >
            <p className="font-medium text-danger">{refusal.title}</p>
            <p className="text-foreground">{refusal.message}</p>
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          {completing ? "Cancel" : "Keep it"}
        </DialogClose>
        <Button
          type="submit"
          variant={completing ? "primary" : "destructive"}
          state={submit.state}
          loadingLabel={completing ? "Saving…" : "Cancelling…"}
          successLabel={completing ? "Done" : "Cancelled"}
          errorLabel="Not saved"
        >
          {completing ? "Mark done" : "Cancel task"}
        </Button>
      </DialogFooter>
    </form>
  );
}
