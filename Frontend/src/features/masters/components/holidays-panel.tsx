"use client";

import {
  Add01Icon,
  ArrowLeft01Icon,
  ArrowRight01Icon,
  Calendar03Icon,
  Delete02Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAddHoliday, useRemoveHoliday } from "@/features/masters/api/holidays.mutations";
import { holidaysQueryOptions } from "@/features/masters/api/holidays.queries";
import {
  HOLIDAY_NAME_MAX_LENGTH,
  type AddHolidayRequest,
  type Holiday,
} from "@/features/masters/api/holidays.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatCalendarDay, shiftCalendarDay, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/masters/components/holidays-panel.tsx",
  dataId: "MSTR-019",
});

/** Whether a day is a Sunday, which never needs a holiday (422 `holiday_sunday`). */
export function isSunday(day: string): boolean {
  return new Date(`${day}T00:00:00Z`).getUTCDay() === 0;
}

type HolidayField = "day" | "name";

/** What is wrong before the holiday can be sent. */
export function holidayProblems(
  draft: AddHolidayRequest,
  today: string,
): Partial<Record<HolidayField, string>> {
  return {
    ...(draft.day === ""
      ? { day: "Choose the day." }
      : draft.day <= today
        ? { day: "Tomorrow or later: a complaint already running keeps its targets." }
        : isSunday(draft.day)
          ? { day: "Sundays never count already." }
          : {}),
    ...(draft.name.trim() === "" ? { name: "Name the holiday." } : {}),
  };
}

/** The backend's refusals, on the field they concern. */
export function holidayRefusal(error: unknown): Partial<Record<HolidayField, string>> | null {
  if (!isApiError(error)) return null;
  switch (error.code) {
    case "holiday_exists":
      return { day: "That day is already a holiday." };
    case "holiday_in_past":
      return { day: "Tomorrow or later: a complaint already running keeps its targets." };
    case "holiday_sunday":
      return { day: "Sundays never count already." };
    default: {
      const fields = readFieldErrors(error) ?? {};
      const mapped: Partial<Record<HolidayField, string>> = {
        ...(fields.day === undefined ? {} : { day: fields.day }),
        ...(fields.name === undefined ? {} : { name: fields.name }),
      };
      return Object.keys(mapped).length > 0 ? mapped : null;
    }
  }
}

/**
 * MSTR-019 · Holidays, a year at a time: the days complaint targets skip, as they skip Sundays.
 * Those who edit masters add one from tomorrow on and remove one still ahead; a past holiday
 * stays, since targets were counted with it.
 */
export function HolidaysPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const today = todayInIndia();
  const [year, setYear] = useState(() => Number(today.slice(0, 4)));
  const query = useQuery(holidaysQueryOptions(year));
  const [adding, setAdding] = useState(false);
  const [removing, setRemoving] = useState<Holiday | null>(null);

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div className="flex flex-col gap-0.5">
          <CardTitle>Holidays</CardTitle>
          <CardDescription>
            Complaint targets count working hours, Monday to Saturday, 9:30 to 6:30. A holiday
            counts like a Sunday.
          </CardDescription>
        </div>
        {canEdit ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setAdding(true);
            }}
          >
            <Icon icon={Add01Icon} />
            Add holiday
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center gap-1" role="group" aria-label="Year">
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Holidays in ${String(year - 1)}`}
            onClick={() => {
              setYear(year - 1);
            }}
          >
            <Icon icon={ArrowLeft01Icon} />
          </Button>
          <span className="min-w-14 text-center text-sm font-semibold text-foreground tabular-nums">
            {year}
          </span>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={`Holidays in ${String(year + 1)}`}
            onClick={() => {
              setYear(year + 1);
            }}
          >
            <Icon icon={ArrowRight01Icon} />
          </Button>
        </div>
        {query.status === "pending" ? (
          <div aria-busy="true" aria-label="Loading the holidays" className="flex flex-col gap-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        ) : query.data.length === 0 ? (
          <EmptyState
            icon={Calendar03Icon}
            title={`No holidays in ${String(year)}`}
            description={
              canEdit ? "Add the year's holidays ahead of time." : "Only Sundays are skipped."
            }
            className="py-8"
          />
        ) : (
          <ul
            aria-label={`Holidays in ${String(year)}`}
            className="flex flex-col divide-y divide-border"
          >
            {query.data.map((holiday) => {
              const ahead = holiday.day > today;
              return (
                <li
                  key={holiday.day}
                  className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
                >
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-sm font-medium text-foreground">{holiday.name}</span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {formatCalendarDay(holiday.day)}
                    </span>
                  </div>
                  {ahead ? (
                    canEdit ? (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Remove ${holiday.name}`}
                        onClick={() => {
                          setRemoving(holiday);
                        }}
                      >
                        <Icon icon={Delete02Icon} />
                      </Button>
                    ) : (
                      <Badge variant="info" size="sm">
                        Ahead
                      </Badge>
                    )
                  ) : (
                    <Badge variant="neutral" size="sm">
                      Past
                    </Badge>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <p className="text-xs text-muted-foreground">
          A new holiday applies to complaints submitted after it is added.
        </p>
      </CardContent>
      <Dialog open={adding} onOpenChange={setAdding}>
        <DialogContent size="sm">
          {adding ? (
            <AddHolidayForm
              onDone={(day) => {
                setAdding(false);
                setYear(Number(day.slice(0, 4)));
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
      <Dialog
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) setRemoving(null);
        }}
      >
        <DialogContent size="sm">
          {removing === null ? null : (
            <RemoveHolidayForm
              holiday={removing}
              onDone={() => {
                setRemoving(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function AddHolidayForm({ onDone }: { onDone: (day: string) => void }): React.JSX.Element {
  const today = todayInIndia();
  const [draft, setDraft] = useState<AddHolidayRequest>({ day: "", name: "" });
  const [problems, setProblems] = useState<Partial<Record<HolidayField, string>>>({});
  const mutation = useAddHoliday();
  const idempotency = useIdempotencyKey();

  const save = useAsyncAction({
    action: () => {
      const body = { day: draft.day, name: draft.name.trim() };
      return mutation.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleAddHoliday",
    dataId: "MSTR-019",
    onSuccess: (holiday) => {
      idempotency.reset();
      toast.success("Holiday added", {
        description: `${holiday.name}, ${formatCalendarDay(holiday.day)}.`,
      });
      onDone(holiday.day);
    },
    onError: (error) => {
      const refusal = holidayRefusal(error);
      if (refusal !== null) {
        setProblems(refusal);
        return;
      }
      toast.error("Holiday not added", { description: toUserFacingError(error).description });
    },
  });

  const invalid = (field: HolidayField): true | undefined =>
    problems[field] === undefined ? undefined : true;

  return (
    <form
      noValidate
      aria-label="Add a holiday"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        const found = holidayProblems(draft, today);
        setProblems(found);
        if (Object.keys(found).length === 0) void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Add a holiday</DialogTitle>
        <DialogDescription>It applies to complaints submitted after it is added.</DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={invalid("day")}>
          <FieldLabel htmlFor="holiday-day">Day</FieldLabel>
          <Input
            id="holiday-day"
            type="date"
            min={shiftCalendarDay(today, 1)}
            value={draft.day}
            aria-invalid={invalid("day")}
            aria-describedby={invalid("day") ? "holiday-day-error" : "holiday-day-hint"}
            onChange={(event) => {
              setDraft((before) => ({ ...before, day: event.target.value }));
            }}
          />
          {problems.day === undefined ? (
            <FieldDescription id="holiday-day-hint">
              Tomorrow or later, not a Sunday.
            </FieldDescription>
          ) : null}
          <FieldError id="holiday-day-error">{problems.day}</FieldError>
        </Field>
        <Field data-invalid={invalid("name")}>
          <FieldLabel htmlFor="holiday-name">Name</FieldLabel>
          <Input
            id="holiday-name"
            value={draft.name}
            maxLength={HOLIDAY_NAME_MAX_LENGTH}
            autoComplete="off"
            placeholder="Diwali"
            aria-invalid={invalid("name")}
            aria-describedby={invalid("name") ? "holiday-name-error" : undefined}
            onChange={(event) => {
              setDraft((before) => ({ ...before, name: event.target.value }));
            }}
          />
          <FieldError id="holiday-name-error">{problems.name}</FieldError>
        </Field>
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={save.state}
          loadingLabel="Adding…"
          successLabel="Added"
          errorLabel="Not added"
        >
          Add the holiday
        </Button>
      </DialogFooter>
    </form>
  );
}

function RemoveHolidayForm({
  holiday,
  onDone,
}: {
  holiday: Holiday;
  onDone: () => void;
}): React.JSX.Element {
  const mutation = useRemoveHoliday();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<string | null>(null);
  const submit = useAsyncAction({
    action: () =>
      mutation.mutateAsync({
        day: holiday.day,
        idempotencyKey: idempotency.keyFor({ remove: holiday.day }),
      }),
    logger: log,
    fn: "handleRemoveHoliday",
    dataId: "MSTR-019",
    onSuccess: () => {
      toast.success("Holiday removed", { description: holiday.name });
      onDone();
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.code === "holiday_in_past"
          ? "It has started or passed, so complaints were counted with it. It stays."
          : toUserFacingError(error).description,
      );
    },
  });

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>Remove {holiday.name}?</DialogTitle>
        <DialogDescription>
          {formatCalendarDay(holiday.day)} becomes a working day again for complaints submitted from
          now on.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it
        </DialogClose>
        <Button
          variant="destructive"
          state={submit.state}
          loadingLabel="Removing…"
          successLabel="Removed"
          errorLabel="Not removed"
          onClick={() => {
            setRefusal(null);
            void submit.run();
          }}
        >
          Remove
        </Button>
      </DialogFooter>
    </div>
  );
}
