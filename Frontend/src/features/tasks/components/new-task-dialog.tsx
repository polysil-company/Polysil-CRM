"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { ErrorReference } from "@/components/patterns/error-state";
import { Button, type ButtonProps } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import { useCreateTask } from "@/features/tasks/api/tasks.mutations";
import { taskAssigneesQueryOptions } from "@/features/tasks/api/tasks.queries";
import {
  DEFAULT_DUE_TIME,
  TASK_TYPES,
  taskFormSchema,
  type CreateTaskRequest,
  type TaskFormValues,
  type TaskSubject,
} from "@/features/tasks/api/tasks.schemas";
import { TASK_TYPE_LABELS, taskRefusal } from "@/features/tasks/lib/task-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatFullDate, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/tasks/components/new-task-dialog.tsx",
  dataId: "TASK-004",
});

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

const TYPE_ITEMS = TASK_TYPES.map((value) => ({ value, label: TASK_TYPE_LABELS[value] }));

/** Form fields the backend's field names land on. */
const SERVER_FIELDS: Readonly<Record<string, keyof TaskFormValues>> = {
  title: "title",
  task_type: "type",
  due_at: "dueDate",
  assigned_to: "assignedTo",
  meeting_type_id: "meetingTypeId",
  notes: "notes",
};

export interface NewTaskDialogProps {
  /** What the task is about, when opened from a lead; null for a task of the user's own. */
  subject: TaskSubject | null;
  /** The day it starts on: the day being looked at. Today by default. */
  defaultDate?: string;
  /** The signed-in user, who it is for unless changed. */
  meId: string | null;
  /** Who it is for at first, when not the user: the person whose day is open. */
  defaultAssigneeId?: string | null;
  /** The trigger's look. */
  triggerVariant?: ButtonProps["variant"];
}

/**
 * TASK-004 · New task: what to do, the kind, when (a time is optional: without one it is due
 * at 18:00), who does it (the user or someone below them), and notes. Opened from a lead, it
 * is about that lead, and a meeting there names the kind of meeting. Server field errors land
 * on their fields; a retry of the same details reuses its Idempotency-Key.
 */
export function NewTaskDialog({
  subject,
  defaultDate,
  meId,
  defaultAssigneeId = null,
  triggerVariant = "primary",
}: NewTaskDialogProps): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [formError, setFormError] = useState<unknown>(null);
  const timer = useRef<number | undefined>(undefined);
  const idempotency = useIdempotencyKey();
  const createTask = useCreateTask();

  const blank = (): TaskFormValues => ({
    title: "",
    type: subject === null ? "followup" : "call",
    dueDate: defaultDate ?? todayInIndia(),
    dueTime: "",
    assignedTo: defaultAssigneeId ?? meId ?? "",
    meetingTypeId: "",
    notes: "",
  });
  const form = useForm<TaskFormValues, unknown, CreateTaskRequest>({
    resolver: zodResolver(taskFormSchema(subject)),
    defaultValues: blank(),
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const type = useWatch({ control: form.control, name: "type" });

  useEffect(() => {
    return () => {
      window.clearTimeout(timer.current);
    };
  }, []);

  const submit = useAsyncAction({
    action: (body: CreateTaskRequest) =>
      createTask.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) }),
    logger: log,
    fn: "handleCreateTask",
    dataId: "TASK-004",
    onSuccess: (task) => {
      idempotency.reset();
      toast.success("Task added", {
        description: `${task.title} · ${formatFullDate(task.dueAt)}`,
      });
      timer.current = window.setTimeout(() => {
        setOpen(false);
        form.reset(blank());
      }, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      const view = taskRefusal(error);
      const fields = Object.entries(view.fields ?? {}).flatMap(([path, message]) => {
        const field = SERVER_FIELDS[path];
        return field === undefined ? [] : [{ field, message }];
      });
      fields.forEach(({ field, message }, index) => {
        form.setError(field, { type: "server", message }, { shouldFocus: index === 0 });
      });
      if (fields.length === 0) setFormError(error);
    },
  });

  const handleOpenChange = (next: boolean): void => {
    if (submit.isBusy) return; // Never close in the middle of a save.
    if (next) {
      form.reset(blank());
      idempotency.reset();
    }
    setFormError(null);
    submit.reset();
    setOpen(next);
  };

  const formErrorView = formError === null ? null : toUserFacingError(formError);
  const refusal = formError === null ? null : taskRefusal(formError);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button variant={triggerVariant} />}>
        <Icon icon={Add01Icon} />
        {subject === null ? "New task" : "Add task"}
      </DialogTrigger>
      <DialogContent>
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            setFormError(null);
            void form.handleSubmit((body) => submit.run(body))(event);
          }}
        >
          <DialogHeader>
            <DialogTitle>{subject === null ? "New task" : "Add a task"}</DialogTitle>
            <DialogDescription>
              {subject === null
                ? "A call, visit, meeting or follow-up, for you or someone in your team."
                : `About ${subject.label}.`}
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            <FieldGroup className="grid gap-4 sm:grid-cols-2">
              <Field data-invalid={errors.title ? true : undefined} className="sm:col-span-2">
                <FieldLabel htmlFor="task-title">What to do</FieldLabel>
                <Input
                  id="task-title"
                  placeholder="Call Ramesh about the revised quotation"
                  aria-invalid={errors.title ? true : undefined}
                  aria-describedby={errors.title ? "task-title-error" : undefined}
                  {...form.register("title")}
                />
                <FieldError id="task-title-error">{errors.title?.message}</FieldError>
              </Field>

              <Controller
                control={form.control}
                name="type"
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.error ? true : undefined}>
                    <FieldLabel htmlFor="task-type">Kind</FieldLabel>
                    <Select
                      items={TYPE_ITEMS}
                      value={field.value}
                      onValueChange={(value) => {
                        if (value !== null) field.onChange(value);
                      }}
                    >
                      <SelectTrigger
                        id="task-type"
                        aria-invalid={fieldState.error ? true : undefined}
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {TYPE_ITEMS.map((item) => (
                          <SelectItem key={item.value} value={item.value}>
                            {item.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldError>{fieldState.error?.message}</FieldError>
                  </Field>
                )}
              />

              <Controller
                control={form.control}
                name="assignedTo"
                render={({ field, fieldState }) => (
                  <AssigneeField
                    value={field.value}
                    onChange={field.onChange}
                    meId={meId}
                    error={fieldState.error?.message}
                  />
                )}
              />

              {subject !== null && type === "meeting" ? (
                <Controller
                  control={form.control}
                  name="meetingTypeId"
                  render={({ field, fieldState }) => (
                    <MeetingTypeField
                      value={field.value}
                      onChange={field.onChange}
                      error={fieldState.error?.message}
                    />
                  )}
                />
              ) : null}

              <Field data-invalid={errors.dueDate ? true : undefined}>
                <FieldLabel htmlFor="task-due-date">Due on</FieldLabel>
                <Input
                  id="task-due-date"
                  type="date"
                  aria-invalid={errors.dueDate ? true : undefined}
                  aria-describedby={errors.dueDate ? "task-due-date-error" : undefined}
                  {...form.register("dueDate")}
                />
                <FieldError id="task-due-date-error">{errors.dueDate?.message}</FieldError>
              </Field>

              <Field data-invalid={errors.dueTime ? true : undefined}>
                <FieldLabel htmlFor="task-due-time">
                  At
                  <span className="font-normal text-subtle-foreground">(optional)</span>
                </FieldLabel>
                <Input
                  id="task-due-time"
                  type="time"
                  aria-invalid={errors.dueTime ? true : undefined}
                  aria-describedby={errors.dueTime ? "task-due-time-error" : "task-due-time-hint"}
                  {...form.register("dueTime")}
                />
                {errors.dueTime ? null : (
                  <FieldDescription id="task-due-time-hint">
                    Left empty, it is due at {DEFAULT_DUE_TIME}.
                  </FieldDescription>
                )}
                <FieldError id="task-due-time-error">{errors.dueTime?.message}</FieldError>
              </Field>

              <Field data-invalid={errors.notes ? true : undefined} className="sm:col-span-2">
                <FieldLabel htmlFor="task-notes">
                  Notes
                  <span className="font-normal text-subtle-foreground">(optional)</span>
                </FieldLabel>
                <Textarea
                  id="task-notes"
                  rows={3}
                  aria-invalid={errors.notes ? true : undefined}
                  aria-describedby={errors.notes ? "task-notes-error" : undefined}
                  {...form.register("notes")}
                />
                <FieldError id="task-notes-error">{errors.notes?.message}</FieldError>
              </Field>
            </FieldGroup>

            {formErrorView === null || refusal === null ? null : (
              <div
                role="alert"
                className="mt-4 flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
              >
                <p className="font-medium text-danger">{refusal.title}</p>
                <p className="text-foreground">{refusal.message}</p>
                {formErrorView.reference === undefined ? null : (
                  <ErrorReference reference={formErrorView.reference} />
                )}
              </div>
            )}
          </DialogBody>

          <DialogFooter>
            <DialogClose
              render={<Button type="button" variant="outline" disabled={submit.isBusy} />}
            >
              Cancel
            </DialogClose>
            <Button
              type="submit"
              state={submit.state}
              loadingLabel="Adding…"
              successLabel="Added"
              errorLabel="Not saved"
            >
              Add task
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Who does it: the user first, then the people below them. One choice reads as plain text. */
function AssigneeField({
  value,
  onChange,
  meId,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  meId: string | null;
  error: string | undefined;
}): React.JSX.Element {
  const query = useQuery(taskAssigneesQueryOptions());
  const items = (query.data ?? []).map((person) => ({
    value: person.id,
    label: person.id === meId ? `${person.name} (you)` : person.name,
  }));

  return (
    <Field data-invalid={error ? true : undefined}>
      <FieldLabel htmlFor="task-assignee">For</FieldLabel>
      <Select
        items={items}
        value={value === "" ? null : value}
        disabled={query.isPending || query.isError}
        onValueChange={(next) => {
          if (typeof next === "string") onChange(next);
        }}
      >
        <SelectTrigger
          id="task-assignee"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "task-assignee-error" : undefined}
        >
          <SelectValue
            placeholder={
              query.isPending ? "Loading…" : query.isError ? "Couldn't load people" : "Choose"
            }
          />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <FieldError id="task-assignee-error">{error}</FieldError>
    </Field>
  );
}

/** The kind of meeting on a lead, from the admin-edited list; active ones only. */
function MeetingTypeField({
  value,
  onChange,
  error,
}: {
  value: string;
  onChange: (value: string) => void;
  error: string | undefined;
}): React.JSX.Element {
  const query = useQuery(lookupListQueryOptions("meeting-types"));
  const items = (query.data ?? [])
    .filter((item) => item.isActive)
    .map((item) => ({ value: item.id, label: item.name }));

  return (
    <Field data-invalid={error ? true : undefined} className="sm:col-span-2">
      <FieldLabel htmlFor="task-meeting-type">Kind of meeting</FieldLabel>
      <Select
        items={items}
        value={value === "" ? null : value}
        disabled={query.isPending || query.isError}
        onValueChange={(next) => {
          if (typeof next === "string") onChange(next);
        }}
      >
        <SelectTrigger
          id="task-meeting-type"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "task-meeting-type-error" : undefined}
        >
          <SelectValue
            placeholder={
              query.isPending
                ? "Loading…"
                : query.isError
                  ? "Couldn't load the list"
                  : "Survey & Design, Follow-up…"
            }
          />
        </SelectTrigger>
        <SelectContent>
          {items.map((item) => (
            <SelectItem key={item.value} value={item.value}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <FieldError id="task-meeting-type-error">{error}</FieldError>
    </Field>
  );
}
