"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Button } from "@/components/ui/button";
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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { usePatchTask } from "@/features/tasks/api/tasks.mutations";
import { taskAssigneesQueryOptions } from "@/features/tasks/api/tasks.queries";
import {
  DEFAULT_DUE_TIME,
  TASK_TEXT_MAX,
  TASK_TITLE_MAX,
  type PatchTaskRequest,
  type Task,
} from "@/features/tasks/api/tasks.schemas";
import { TASK_TYPE_LABELS, taskRefusal, taskSubjectLabel } from "@/features/tasks/lib/task-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { calendarDayOf, timeOfDayOf } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/tasks/components/edit-task-dialog.tsx",
  dataId: "TASK-006",
});

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

interface EditForm {
  title: string;
  dueDate: string;
  dueTime: string;
  assignedTo: string;
  notes: string;
}

const editFormSchema: z.ZodType<EditForm, EditForm> = z.object({
  title: z
    .string()
    .trim()
    .min(1, "Say what is to be done.")
    .max(TASK_TITLE_MAX, `Keep it under ${String(TASK_TITLE_MAX)} characters.`),
  dueDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Choose the day it is due."),
  dueTime: z.union([
    z.literal(""),
    z.string().regex(/^([01]\d|2[0-3]):[0-5]\d$/, "Enter a time like 10:30."),
  ]),
  assignedTo: z.string().min(1, "Choose who does it."),
  notes: z
    .string()
    .trim()
    .max(TASK_TEXT_MAX, `Keep notes under ${String(TASK_TEXT_MAX)} characters.`),
});

/** The form as the task stands. */
function formOf(task: Task): EditForm {
  return {
    title: task.title,
    dueDate: calendarDayOf(task.dueAt),
    dueTime: timeOfDayOf(task.dueAt),
    assignedTo: task.assignedTo?.id ?? "",
    notes: task.notes ?? "",
  };
}

/**
 * Only what changed, so a save never overwrites a field someone else changed meanwhile;
 * `expected_status` makes the backend refuse it if the task is no longer open.
 */
export function patchOf(task: Task, values: EditForm): PatchTaskRequest | null {
  const before = formOf(task);
  const body: PatchTaskRequest = {};
  if (values.title.trim() !== before.title) body.title = values.title.trim();
  if (values.dueDate !== before.dueDate || values.dueTime !== before.dueTime) {
    body.due_at =
      values.dueTime === "" ? values.dueDate : `${values.dueDate}T${values.dueTime}:00+05:30`;
  }
  if (values.notes.trim() !== before.notes) {
    body.notes = values.notes.trim() === "" ? null : values.notes.trim();
  }
  if (values.assignedTo !== before.assignedTo) body.assigned_to = values.assignedTo;
  return Object.keys(body).length === 0 ? null : { ...body, expected_status: "open" };
}

const SERVER_FIELDS: Readonly<Record<string, keyof EditForm>> = {
  title: "title",
  due_at: "dueDate",
  assigned_to: "assignedTo",
  notes: "notes",
};

export interface EditTaskDialogProps {
  /** The task being edited; null when closed. */
  task: Task | null;
  meId: string | null;
  onClose: () => void;
}

/**
 * TASK-006 · Change an open task: what to do, when, notes — or give it to someone else
 * (the people below the user). Only what changed is sent. A task done or cancelled
 * meanwhile closes the dialog with a note; someone who can't open the task's lead is
 * refused on the assignee field.
 */
export function EditTaskDialog({ task, meId, onClose }: EditTaskDialogProps): React.JSX.Element {
  return (
    <Dialog
      open={task !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        {task === null ? null : (
          <EditForm key={task.id} task={task} meId={meId} onClose={onClose} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function EditForm({
  task,
  meId,
  onClose,
}: {
  task: Task;
  meId: string | null;
  onClose: () => void;
}): React.JSX.Element {
  const patch = usePatchTask();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const form = useForm<EditForm>({
    resolver: zodResolver(editFormSchema),
    defaultValues: formOf(task),
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    return () => {
      window.clearTimeout(timer.current);
    };
  }, []);
  const subject = taskSubjectLabel(task);

  const submit = useAsyncAction({
    action: (body: PatchTaskRequest) =>
      patch.mutateAsync({
        taskId: task.id,
        body,
        idempotencyKey: idempotency.keyFor({ task: task.id, ...body }),
      }),
    logger: log,
    fn: "handleEditTask",
    dataId: "TASK-006",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(
        saved.assignedTo?.id === task.assignedTo?.id
          ? "Task updated"
          : `Given to ${saved.assignedTo?.name ?? "someone else"}`,
        { description: saved.title },
      );
      timer.current = window.setTimeout(onClose, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      const view = taskRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      const fields = Object.entries(view.fields ?? {}).flatMap(([path, message]) => {
        const field = SERVER_FIELDS[path];
        return field === undefined ? [] : [{ field, message }];
      });
      fields.forEach(({ field, message }, index) => {
        form.setError(field, { type: "server", message }, { shouldFocus: index === 0 });
      });
      if (fields.length === 0) setRefusal({ title: view.title, message: view.message });
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => {
          const body = patchOf(task, values);
          if (body === null) {
            onClose(); // Nothing changed: nothing to send.
            return;
          }
          return submit.run(body);
        })(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>Edit task</DialogTitle>
        <DialogDescription>
          {TASK_TYPE_LABELS[task.type]}
          {task.meetingType === null ? "" : ` · ${task.meetingType.name}`}
          {subject === null ? "" : ` · ${subject}`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={errors.title ? true : undefined} className="sm:col-span-2">
            <FieldLabel htmlFor="edit-task-title">What to do</FieldLabel>
            <Input
              id="edit-task-title"
              aria-invalid={errors.title ? true : undefined}
              aria-describedby={errors.title ? "edit-task-title-error" : undefined}
              {...form.register("title")}
            />
            <FieldError id="edit-task-title-error">{errors.title?.message}</FieldError>
          </Field>

          <Field data-invalid={errors.dueDate ? true : undefined}>
            <FieldLabel htmlFor="edit-task-due-date">Due on</FieldLabel>
            <Input
              id="edit-task-due-date"
              type="date"
              aria-invalid={errors.dueDate ? true : undefined}
              aria-describedby={errors.dueDate ? "edit-task-due-date-error" : undefined}
              {...form.register("dueDate")}
            />
            <FieldError id="edit-task-due-date-error">{errors.dueDate?.message}</FieldError>
          </Field>

          <Field data-invalid={errors.dueTime ? true : undefined}>
            <FieldLabel htmlFor="edit-task-due-time">
              At
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Input
              id="edit-task-due-time"
              type="time"
              aria-invalid={errors.dueTime ? true : undefined}
              aria-describedby={
                errors.dueTime ? "edit-task-due-time-error" : "edit-task-due-time-hint"
              }
              {...form.register("dueTime")}
            />
            {errors.dueTime ? null : (
              <FieldDescription id="edit-task-due-time-hint">
                Left empty, it is due at {DEFAULT_DUE_TIME}.
              </FieldDescription>
            )}
            <FieldError id="edit-task-due-time-error">{errors.dueTime?.message}</FieldError>
          </Field>

          <Controller
            control={form.control}
            name="assignedTo"
            render={({ field, fieldState }) => (
              <ReassignField
                value={field.value}
                onChange={field.onChange}
                meId={meId}
                current={task.assignedTo}
                error={fieldState.error?.message}
              />
            )}
          />

          <Field data-invalid={errors.notes ? true : undefined} className="sm:col-span-2">
            <FieldLabel htmlFor="edit-task-notes">
              Notes
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="edit-task-notes"
              rows={3}
              aria-invalid={errors.notes ? true : undefined}
              aria-describedby={errors.notes ? "edit-task-notes-error" : undefined}
              {...form.register("notes")}
            />
            <FieldError id="edit-task-notes-error">{errors.notes?.message}</FieldError>
          </Field>
        </FieldGroup>
        {refusal === null ? null : (
          <div
            role="alert"
            className="mt-4 flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
          >
            <p className="font-medium text-danger">{refusal.title}</p>
            <p className="text-foreground">{refusal.message}</p>
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * Who does it. The people the user may give tasks to; the current assignee stays listed even
 * when they aren't one of them (a task given by someone higher up), so the field never empties.
 */
function ReassignField({
  value,
  onChange,
  meId,
  current,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  meId: string | null;
  current: Task["assignedTo"];
  error: string | undefined;
}): React.JSX.Element {
  const query = useQuery(taskAssigneesQueryOptions());
  const people = query.data ?? [];
  const listed =
    current === null || people.some((person) => person.id === current.id)
      ? people
      : [current, ...people];
  const items = listed.map((person) => ({
    value: person.id,
    label: person.id === meId ? `${person.name} (you)` : person.name,
  }));

  return (
    <Field data-invalid={error ? true : undefined} className="sm:col-span-2">
      <FieldLabel htmlFor="edit-task-assignee">For</FieldLabel>
      <Select
        items={items}
        value={value === "" ? null : value}
        disabled={query.isPending || query.isError || items.length <= 1}
        onValueChange={(next) => {
          if (typeof next === "string") onChange(next);
        }}
      >
        <SelectTrigger
          id="edit-task-assignee"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "edit-task-assignee-error" : "edit-task-assignee-hint"}
        >
          <SelectValue placeholder={query.isPending ? "Loading…" : "Choose"} />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {error ? null : (
        <FieldDescription id="edit-task-assignee-hint">
          {items.length <= 1
            ? "Only a manager can give it to someone else."
            : "They must be able to open what the task is about."}
        </FieldDescription>
      )}
      <FieldError id="edit-task-assignee-error">{error}</FieldError>
    </Field>
  );
}
