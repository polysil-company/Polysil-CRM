"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon, Delete02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { Controller, useFieldArray, useForm, useFormState } from "react-hook-form";
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
import { useCreateMinutes } from "@/features/tasks/api/tasks.mutations";
import { taskAssigneesQueryOptions } from "@/features/tasks/api/tasks.queries";
import {
  ACTION_ITEMS_MAX,
  ACTION_ITEM_TYPES,
  ATTENDEES_MAX,
  ATTENDEE_MAX,
  TASK_TEXT_MAX,
  TASK_TITLE_MAX,
  type ActionItemType,
  type CreateMinutesRequest,
  type Task,
} from "@/features/tasks/api/tasks.schemas";
import { TASK_TYPE_LABELS, taskRefusal } from "@/features/tasks/lib/task-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { calendarDayOf, timeOfDayOf, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/tasks/components/minutes-dialog.tsx",
  dataId: "TASK-007",
});

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;
const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;

const ITEM_TYPE_OPTIONS = ACTION_ITEM_TYPES.map((value) => ({
  value,
  label: TASK_TYPE_LABELS[value],
}));

interface ActionItemForm {
  title: string;
  dueDate: string;
  assignedTo: string;
  type: ActionItemType;
}

interface MinutesForm {
  heldDate: string;
  heldTime: string;
  attendees: string;
  notes: string;
  actionItems: ActionItemForm[];
}

/** One name per line; blank lines dropped. */
function attendeeList(text: string): string[] {
  return text
    .split("\n")
    .map((name) => name.trim())
    .filter((name) => name !== "");
}

const minutesFormSchema: z.ZodType<MinutesForm, MinutesForm> = z.object({
  heldDate: z.string().regex(DATE_PATTERN, "Choose the day it was held."),
  heldTime: z.string().regex(TIME_PATTERN, "Enter the time, like 15:00."),
  attendees: z.string().superRefine((text, ctx) => {
    const names = attendeeList(text);
    if (names.length > ATTENDEES_MAX) {
      ctx.addIssue({ code: "custom", message: `At most ${String(ATTENDEES_MAX)} people.` });
    }
    if (names.some((name) => name.length > ATTENDEE_MAX)) {
      ctx.addIssue({
        code: "custom",
        message: `Keep each name under ${String(ATTENDEE_MAX)} characters.`,
      });
    }
  }),
  notes: z
    .string()
    .trim()
    .min(1, "Write what was discussed and agreed.")
    .max(TASK_TEXT_MAX, `Keep it under ${String(TASK_TEXT_MAX)} characters.`),
  actionItems: z
    .array(
      z.object({
        title: z
          .string()
          .trim()
          .min(1, "Say what is to be done.")
          .max(TASK_TITLE_MAX, `Keep it under ${String(TASK_TITLE_MAX)} characters.`),
        dueDate: z.string().regex(DATE_PATTERN, "Choose when it is due."),
        assignedTo: z.string().min(1, "Choose who does it."),
        type: z.enum(ACTION_ITEM_TYPES),
      }),
    )
    .max(ACTION_ITEMS_MAX, `At most ${String(ACTION_ITEMS_MAX)} action items.`),
});

/** The backend's `fields` paths onto the form's: `action_items.1.title` → `actionItems.1.title`. */
function formPathOf(path: string): string | null {
  const item = /^action_items\.(\d+)\.(title|due_at|assigned_to|task_type)$/.exec(path);
  if (item !== null) {
    const field = {
      title: "title",
      due_at: "dueDate",
      assigned_to: "assignedTo",
      task_type: "type",
    }[item[2] ?? "title"];
    return `actionItems.${item[1] ?? "0"}.${field ?? "title"}`;
  }
  const top: Readonly<Record<string, string>> = {
    held_at: "heldDate",
    notes: "notes",
    attendees: "attendees",
  };
  return top[path] ?? null;
}

export interface MinutesSubject {
  readonly leadId: string;
  readonly leadName: string;
  /** The meeting these minutes record, marked done on save; null for a meeting not planned. */
  readonly meeting: Task | null;
}

export interface MinutesDialogProps {
  /** What the minutes are about; null when closed. */
  subject: MinutesSubject | null;
  meId: string | null;
  onClose: () => void;
}

/**
 * TASK-007 · Record a meeting: when it was held, who was there (one per line), what was
 * discussed, and action items — each becomes a task for someone, due on a day. One save: if
 * one action item is refused, nothing is saved, and the reason sits on that item. Recorded
 * from a planned meeting, that meeting is marked done.
 */
export function MinutesDialog({ subject, meId, onClose }: MinutesDialogProps): React.JSX.Element {
  return (
    <Dialog
      open={subject !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent>
        {subject === null ? null : (
          <MinutesFormBody
            key={subject.meeting?.id ?? subject.leadId}
            subject={subject}
            meId={meId}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function MinutesFormBody({
  subject,
  meId,
  onClose,
}: {
  subject: MinutesSubject;
  meId: string | null;
  onClose: () => void;
}): React.JSX.Element {
  const create = useCreateMinutes();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const [today] = useState(todayInIndia);
  const { meeting } = subject;
  const form = useForm<MinutesForm>({
    resolver: zodResolver(minutesFormSchema),
    defaultValues: {
      heldDate: meeting === null ? today : calendarDayOf(meeting.dueAt),
      heldTime: meeting === null ? "" : timeOfDayOf(meeting.dueAt),
      attendees: "",
      notes: "",
      actionItems: [],
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const items = useFieldArray({ control: form.control, name: "actionItems" });
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    return () => {
      window.clearTimeout(timer.current);
    };
  }, []);

  const submit = useAsyncAction({
    action: (body: CreateMinutesRequest) =>
      create.mutateAsync({
        leadId: subject.leadId,
        body,
        idempotencyKey: idempotency.keyFor(body),
      }),
    logger: log,
    fn: "handleRecordMinutes",
    dataId: "TASK-007",
    onSuccess: (minutes) => {
      idempotency.reset();
      const count = minutes.actionItems.length;
      toast.success("Minutes recorded", {
        description:
          count === 0
            ? subject.leadName
            : `${subject.leadName} · ${String(count)} ${count === 1 ? "task" : "tasks"} added`,
      });
      timer.current = window.setTimeout(onClose, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      const view = taskRefusal(error);
      const fields = Object.entries(view.fields ?? {}).flatMap(([path, message]) => {
        const field = formPathOf(path);
        return field === null ? [] : [{ field, message }];
      });
      fields.forEach(({ field, message }, index) => {
        if (isFormPath(field)) {
          form.setError(field, { type: "server", message }, { shouldFocus: index === 0 });
        }
      });
      if (fields.length === 0) setRefusal({ title: view.title, message: view.message });
    },
  });

  const toRequest = (values: MinutesForm): CreateMinutesRequest => ({
    lead_id: subject.leadId,
    task_id: meeting?.id ?? null,
    held_at: `${values.heldDate}T${values.heldTime}:00+05:30`,
    attendees: attendeeList(values.attendees),
    notes: values.notes.trim(),
    action_items: values.actionItems.map((item) => ({
      title: item.title.trim(),
      due_at: item.dueDate,
      assigned_to: item.assignedTo,
      task_type: item.type,
    })),
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => submit.run(toRequest(values)))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>Record minutes</DialogTitle>
        <DialogDescription>
          {meeting === null
            ? `A meeting about ${subject.leadName}.`
            : `${meeting.title}. Saving marks the meeting done.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={errors.heldDate ? true : undefined}>
            <FieldLabel htmlFor="minutes-held-date">Held on</FieldLabel>
            <Input
              id="minutes-held-date"
              type="date"
              aria-invalid={errors.heldDate ? true : undefined}
              aria-describedby={errors.heldDate ? "minutes-held-date-error" : undefined}
              {...form.register("heldDate")}
            />
            <FieldError id="minutes-held-date-error">{errors.heldDate?.message}</FieldError>
          </Field>
          <Field data-invalid={errors.heldTime ? true : undefined}>
            <FieldLabel htmlFor="minutes-held-time">At</FieldLabel>
            <Input
              id="minutes-held-time"
              type="time"
              aria-invalid={errors.heldTime ? true : undefined}
              aria-describedby={errors.heldTime ? "minutes-held-time-error" : undefined}
              {...form.register("heldTime")}
            />
            <FieldError id="minutes-held-time-error">{errors.heldTime?.message}</FieldError>
          </Field>

          <Field data-invalid={errors.attendees ? true : undefined} className="sm:col-span-2">
            <FieldLabel htmlFor="minutes-attendees">
              Who was there
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="minutes-attendees"
              rows={3}
              placeholder={"Ramesh Patel\nHis son, Kiran"}
              aria-invalid={errors.attendees ? true : undefined}
              aria-describedby={
                errors.attendees ? "minutes-attendees-error" : "minutes-attendees-hint"
              }
              {...form.register("attendees")}
            />
            {errors.attendees ? null : (
              <FieldDescription id="minutes-attendees-hint">One person per line.</FieldDescription>
            )}
            <FieldError id="minutes-attendees-error">{errors.attendees?.message}</FieldError>
          </Field>

          <Field data-invalid={errors.notes ? true : undefined} className="sm:col-span-2">
            <FieldLabel htmlFor="minutes-notes">What was discussed</FieldLabel>
            <Textarea
              id="minutes-notes"
              rows={4}
              aria-invalid={errors.notes ? true : undefined}
              aria-describedby={errors.notes ? "minutes-notes-error" : undefined}
              {...form.register("notes")}
            />
            <FieldError id="minutes-notes-error">{errors.notes?.message}</FieldError>
          </Field>
        </FieldGroup>

        <fieldset className="mt-5 flex flex-col gap-3">
          <legend className="mb-1 text-sm font-medium text-foreground">
            Action items
            <span className="ml-1.5 font-normal text-muted-foreground">each becomes a task</span>
          </legend>
          {items.fields.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              None yet. Add what was agreed: a quotation to send, papers to collect.
            </p>
          ) : null}
          <ol className="flex flex-col gap-3">
            {items.fields.map((item, index) => (
              <ActionItemRow
                key={item.id}
                index={index}
                form={form}
                meId={meId}
                onRemove={() => {
                  items.remove(index);
                }}
              />
            ))}
          </ol>
          {items.fields.length < ACTION_ITEMS_MAX ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start"
              onClick={() => {
                items.append(
                  { title: "", dueDate: today, assignedTo: meId ?? "", type: "followup" },
                  { shouldFocus: true },
                );
              }}
            >
              <Icon icon={Add01Icon} />
              Add an action item
            </Button>
          ) : null}
        </fieldset>

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
          successLabel="Recorded"
          errorLabel="Not saved"
        >
          Save minutes
        </Button>
      </DialogFooter>
    </form>
  );
}

type MinutesFormApi = ReturnType<typeof useForm<MinutesForm>>;

const FORM_PATHS = new Set(["heldDate", "heldTime", "attendees", "notes"]);

/** Narrows a path built from the backend's `fields` to one the form has. */
function isFormPath(
  path: string,
): path is
  | "heldDate"
  | "heldTime"
  | "attendees"
  | "notes"
  | `actionItems.${number}.${"title" | "dueDate" | "assignedTo" | "type"}` {
  return FORM_PATHS.has(path) || /^actionItems\.\d+\.(title|dueDate|assignedTo|type)$/.test(path);
}

function ActionItemRow({
  index,
  form,
  meId,
  onRemove,
}: {
  index: number;
  form: MinutesFormApi;
  meId: string | null;
  onRemove: () => void;
}): React.JSX.Element {
  const { errors } = useFormState({ control: form.control, name: `actionItems.${index}` });
  const itemErrors = errors.actionItems?.[index];
  const number = index + 1;
  const prefix = `minutes-item-${String(index)}`;
  const people = useQuery(taskAssigneesQueryOptions());
  const peopleItems = (people.data ?? []).map((person) => ({
    value: person.id,
    label: person.id === meId ? `${person.name} (you)` : person.name,
  }));

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-muted-foreground">Action item {number}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Remove action item ${String(number)}`}
          onClick={onRemove}
        >
          <Icon icon={Delete02Icon} />
        </Button>
      </div>
      <Field data-invalid={itemErrors?.title ? true : undefined}>
        <FieldLabel htmlFor={`${prefix}-title`}>What to do</FieldLabel>
        <Input
          id={`${prefix}-title`}
          aria-invalid={itemErrors?.title ? true : undefined}
          aria-describedby={itemErrors?.title ? `${prefix}-title-error` : undefined}
          {...form.register(`actionItems.${index}.title`)}
        />
        <FieldError id={`${prefix}-title-error`}>{itemErrors?.title?.message}</FieldError>
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field data-invalid={itemErrors?.dueDate ? true : undefined}>
          <FieldLabel htmlFor={`${prefix}-due`}>Due on</FieldLabel>
          <Input
            id={`${prefix}-due`}
            type="date"
            aria-invalid={itemErrors?.dueDate ? true : undefined}
            aria-describedby={itemErrors?.dueDate ? `${prefix}-due-error` : undefined}
            {...form.register(`actionItems.${index}.dueDate`)}
          />
          <FieldError id={`${prefix}-due-error`}>{itemErrors?.dueDate?.message}</FieldError>
        </Field>
        <Controller
          control={form.control}
          name={`actionItems.${index}.type`}
          render={({ field }) => (
            <Field>
              <FieldLabel htmlFor={`${prefix}-type`}>Kind</FieldLabel>
              <Select
                items={ITEM_TYPE_OPTIONS}
                value={field.value}
                onValueChange={(next) => {
                  if (next !== null) field.onChange(next);
                }}
              >
                <SelectTrigger id={`${prefix}-type`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ITEM_TYPE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          )}
        />
        <Controller
          control={form.control}
          name={`actionItems.${index}.assignedTo`}
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.error ? true : undefined} className="sm:col-span-2">
              <FieldLabel htmlFor={`${prefix}-for`}>For</FieldLabel>
              <Select
                items={peopleItems}
                value={field.value === "" ? null : field.value}
                disabled={people.isPending || people.isError}
                onValueChange={(next) => {
                  if (typeof next === "string") field.onChange(next);
                }}
              >
                <SelectTrigger
                  id={`${prefix}-for`}
                  aria-invalid={fieldState.error ? true : undefined}
                  aria-describedby={fieldState.error ? `${prefix}-for-error` : undefined}
                >
                  <SelectValue placeholder={people.isPending ? "Loading…" : "Choose"} />
                </SelectTrigger>
                <SelectContent>
                  {peopleItems.map((person) => (
                    <SelectItem key={person.value} value={person.value}>
                      {person.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldError id={`${prefix}-for-error`}>{fieldState.error?.message}</FieldError>
            </Field>
          )}
        />
      </div>
    </li>
  );
}
