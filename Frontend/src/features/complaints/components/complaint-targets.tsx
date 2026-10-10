"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { Notice } from "@/components/patterns/notice";
import { QueryView } from "@/components/patterns/query-view";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateSlaPolicy } from "@/features/complaints/api/complaints.mutations";
import { slaPoliciesQueryOptions } from "@/features/complaints/api/complaints.queries";
import {
  COMPLAINT_SEVERITIES,
  type ComplaintSeverity,
  type SlaPolicy,
} from "@/features/complaints/api/complaints.schemas";
import { SEVERITY_BADGE, SEVERITY_LABELS } from "@/features/complaints/lib/complaint-labels";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import { useCan } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatCalendarDay, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { Refusal, useCloseLater } from "./complaint-dialog-parts";

const log = createLogger({
  file: "features/complaints/components/complaint-targets.tsx",
  dataId: "CMPL-008",
});

/** Monday to Saturday, 09:30 to 18:30 IST: nine working hours a day. */
const WORKING_HOURS_PER_DAY = 9;
/** The backend's ceiling: a year of hours. */
const HOURS_MAX = 8760;
/** The Select's value for a target that covers every complaint type. */
const ALL_TYPES = "all";

/** "4 working hours", "27 working hours (3 days)". */
function describeHours(hours: number, businessOnly: boolean): string {
  const unit = businessOnly ? "working hours" : "hours";
  const perDay = businessOnly ? WORKING_HOURS_PER_DAY : 24;
  const days = hours / perDay;
  const word = hours === 1 ? unit.replace(/s$/, "") : unit;
  if (hours < perDay || !Number.isInteger(days)) return `${String(hours)} ${word}`;
  return `${String(hours)} ${word} (${String(days)} ${days === 1 ? "day" : "days"})`;
}

type Phase = "now" | "later" | "past";

function phaseOf(policy: SlaPolicy, today: string): Phase {
  if (policy.effectiveFrom > today) return "later";
  if (policy.effectiveTo !== null && policy.effectiveTo <= today) return "past";
  return "now";
}

/**
 * CMPL-008 · The response and resolution targets each complaint is measured against, by
 * severity (and by type, where one is set). A change takes effect from a day, never in the
 * past; complaints already submitted keep the target they started with. Those who may edit
 * masters set a new one; everyone else reads them.
 */
export function ComplaintTargets(): React.JSX.Element {
  const query = useQuery(slaPoliciesQueryOptions());
  const types = useQuery(lookupListQueryOptions("complaint-types"));
  const canEdit = useCan("masters", "edit");
  const [setting, setSetting] = useState<ComplaintSeverity | null>(null);
  const typeName = (typeId: string | null): string =>
    typeId === null
      ? "Every type"
      : (types.data?.find((type) => type.id === typeId)?.name ?? "One complaint type");

  return (
    <div className="flex flex-col gap-4">
      <p className="max-w-prose text-sm text-muted-foreground">
        Targets count working hours, Monday to Saturday, 09:30 to 18:30, unless a target says
        otherwise. A complaint keeps the target in force when it was first submitted.
      </p>
      <QueryView
        query={query}
        pending={<ComplaintTargetsSkeleton />}
        isEmpty={(rows) => rows.length === 0}
        empty={
          <Notice tone="warning">
            <p className="font-medium">No targets are set</p>
            <p className="text-muted-foreground">
              Complaints show &ldquo;no target&rdquo; until one is.
              {canEdit ? " Set one for each severity." : " Ask the administrator to set them."}
            </p>
          </Notice>
        }
      >
        {(policies) => {
          const today = todayInIndia();
          return (
            <div className="grid gap-4 lg:grid-cols-3">
              {COMPLAINT_SEVERITIES.toReversed().map((severity) => {
                const rows = policies
                  .filter((policy) => policy.severity === severity)
                  .toSorted((a, b) => b.effectiveFrom.localeCompare(a.effectiveFrom));
                return (
                  <SeverityCard
                    key={severity}
                    severity={severity}
                    rows={rows}
                    today={today}
                    typeName={typeName}
                    canEdit={canEdit}
                    onSet={() => {
                      setSetting(severity);
                    }}
                  />
                );
              })}
            </div>
          );
        }}
      </QueryView>

      <Dialog
        open={setting !== null}
        onOpenChange={(open) => {
          if (!open) setSetting(null);
        }}
      >
        <DialogContent size="md">
          {setting === null ? null : (
            <TargetForm
              severity={setting}
              current={
                query.data?.find(
                  (policy) =>
                    policy.severity === setting &&
                    policy.typeId === null &&
                    phaseOf(policy, todayInIndia()) === "now",
                ) ?? null
              }
              typeOptions={(types.data ?? []).map((type) => ({ value: type.id, label: type.name }))}
              onClose={() => {
                setSetting(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

const PHASE_BADGE: Readonly<
  Record<Phase, { label: string; variant: "success" | "info" | "neutral" }>
> = {
  now: { label: "In force", variant: "success" },
  later: { label: "Scheduled", variant: "info" },
  past: { label: "Ended", variant: "neutral" },
};

function SeverityCard({
  severity,
  rows,
  today,
  typeName,
  canEdit,
  onSet,
}: {
  severity: ComplaintSeverity;
  rows: readonly SlaPolicy[];
  today: string;
  typeName: (typeId: string | null) => string;
  canEdit: boolean;
  onSet: () => void;
}): React.JSX.Element {
  const [showPast, setShowPast] = useState(false);
  const visible = rows.filter((row) => showPast || phaseOf(row, today) !== "past");
  const pastCount = rows.length - rows.filter((row) => phaseOf(row, today) !== "past").length;

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <CardTitle level={2}>{SEVERITY_LABELS[severity]}</CardTitle>
          <Badge variant={SEVERITY_BADGE[severity]} size="sm">
            severity
          </Badge>
        </div>
        {canEdit ? (
          <Button
            size="sm"
            variant="outline"
            aria-label={`Set a new target for ${SEVERITY_LABELS[severity].toLowerCase()} severity`}
            onClick={onSet}
          >
            <Icon icon={Add01Icon} />
            New target
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {visible.length === 0 ? (
          <CardDescription>
            No target in force. Complaints show &ldquo;no target&rdquo;.
          </CardDescription>
        ) : (
          <ul
            aria-label={`${SEVERITY_LABELS[severity]} severity targets`}
            className="flex flex-col gap-2"
          >
            {visible.map((row) => {
              const phase = phaseOf(row, today);
              return (
                <li
                  key={row.id}
                  className="flex flex-col gap-1.5 rounded-lg border border-border p-3 text-sm"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={PHASE_BADGE[phase].variant} size="sm" dot>
                      {PHASE_BADGE[phase].label}
                    </Badge>
                    <span className="text-xs text-muted-foreground">{typeName(row.typeId)}</span>
                  </div>
                  <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5">
                    <dt className="text-muted-foreground">First response</dt>
                    <dd className="text-foreground">
                      {describeHours(row.responseHours, row.businessHoursOnly)}
                    </dd>
                    <dt className="text-muted-foreground">Resolution</dt>
                    <dd className="text-foreground">
                      {describeHours(row.resolutionHours, row.businessHoursOnly)}
                    </dd>
                  </dl>
                  <p className="text-xs text-subtle-foreground">
                    From {formatCalendarDay(row.effectiveFrom)}
                    {row.effectiveTo === null ? "" : ` until ${formatCalendarDay(row.effectiveTo)}`}
                    {row.businessHoursOnly ? "" : " · round the clock"}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
        {pastCount > 0 ? (
          <Button
            variant="ghost"
            size="sm"
            className="self-start"
            aria-expanded={showPast}
            onClick={() => {
              setShowPast((value) => !value);
            }}
          >
            {showPast ? "Hide past targets" : `Show ${String(pastCount)} past`}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}

// ── set a target (CMPL-008) ────────────────────────────────────────────────────────

interface TargetForm {
  typeId: string;
  responseHours: string;
  resolutionHours: string;
  businessHoursOnly: boolean;
  effectiveFrom: string;
}

const hoursField = (what: string): z.ZodString =>
  z
    .string()
    .trim()
    .regex(/^\d+$/, `Enter the ${what} in whole hours.`)
    .refine((value) => Number(value) >= 1, `The ${what} is at least 1 hour.`)
    .refine((value) => Number(value) <= HOURS_MAX, "No more than a year of hours.");

function targetSchema(today: string): z.ZodType<TargetForm, TargetForm> {
  return z
    .object({
      typeId: z.string(),
      responseHours: hoursField("first response"),
      resolutionHours: hoursField("resolution"),
      businessHoursOnly: z.boolean(),
      effectiveFrom: z
        .string()
        .min(1, "Choose the day it starts.")
        .refine((value) => value >= today, "It can't start in the past."),
    })
    .superRefine((values, ctx) => {
      const response = Number(values.responseHours);
      const resolution = Number(values.resolutionHours);
      if (Number.isFinite(response) && Number.isFinite(resolution) && resolution < response) {
        ctx.addIssue({
          code: "custom",
          path: ["resolutionHours"],
          message: "Resolution can't be quicker than the first response.",
        });
      }
    });
}

const SERVER_FIELDS = {
  response_hours: "responseHours",
  resolution_hours: "resolutionHours",
  effective_from: "effectiveFrom",
} as const satisfies Readonly<Record<string, keyof TargetForm>>;

function TargetForm({
  severity,
  current,
  typeOptions,
  onClose,
}: {
  severity: ComplaintSeverity;
  current: SlaPolicy | null;
  typeOptions: readonly { value: string; label: string }[];
  onClose: () => void;
}): React.JSX.Element {
  const today = todayInIndia();
  const create = useCreateSlaPolicy();
  const idempotency = useIdempotencyKey();
  const closeLater = useCloseLater(onClose);
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const form = useForm<TargetForm>({
    resolver: zodResolver(targetSchema(today)),
    defaultValues: {
      typeId: ALL_TYPES,
      responseHours: current === null ? "" : String(current.responseHours),
      resolutionHours: current === null ? "" : String(current.resolutionHours),
      businessHoursOnly: current?.businessHoursOnly ?? true,
      effectiveFrom: today,
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const items = [{ value: ALL_TYPES, label: "Every type" }, ...typeOptions];

  const submit = useAsyncAction({
    action: (values: TargetForm) => {
      const body = {
        severity,
        complaint_type_id: values.typeId === ALL_TYPES ? null : values.typeId,
        response_hours: Number(values.responseHours),
        resolution_hours: Number(values.resolutionHours),
        business_hours_only: values.businessHoursOnly,
        effective_from: values.effectiveFrom,
      };
      return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleSetTarget",
    dataId: "CMPL-008",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Target set", {
        description: `${SEVERITY_LABELS[severity]} severity, from ${formatCalendarDay(form.getValues("effectiveFrom"))}.`,
      });
      closeLater();
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "target_exists") {
        form.setError("effectiveFrom", {
          type: "server",
          message: "A target already starts that day. Choose another day.",
        });
        return;
      }
      if (isApiError(error) && error.code === "target_in_the_past") {
        form.setError("effectiveFrom", { type: "server", message: "It can't start in the past." });
        return;
      }
      const fields = readFieldErrors(error);
      let placed = false;
      for (const [api, name] of Object.entries(SERVER_FIELDS)) {
        const message = fields?.[api];
        if (message !== undefined) {
          form.setError(name, { type: "server", message });
          placed = true;
        }
      }
      if (placed) return;
      const view = toUserFacingError(error);
      setRefusal({ title: view.title, message: view.description });
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
        <DialogTitle>New target: {SEVERITY_LABELS[severity].toLowerCase()} severity</DialogTitle>
        <DialogDescription>
          The target in force ends the day this one starts. Complaints already submitted keep
          theirs.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="flex flex-col gap-4">
          <Controller
            control={form.control}
            name="typeId"
            render={({ field }) => (
              <Field>
                <FieldLabel htmlFor="target-type">Complaint type</FieldLabel>
                <Select
                  items={items}
                  value={field.value}
                  onValueChange={(next) => {
                    if (typeof next === "string") field.onChange(next);
                  }}
                >
                  <SelectTrigger id="target-type" aria-describedby="target-type-hint">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {items.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription id="target-type-hint">
                  A target for one type wins over the one for every type.
                </FieldDescription>
              </Field>
            )}
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field data-invalid={errors.responseHours ? true : undefined}>
              <FieldLabel htmlFor="target-response">First response (hours)</FieldLabel>
              <Input
                id="target-response"
                inputMode="numeric"
                autoComplete="off"
                aria-invalid={errors.responseHours ? true : undefined}
                aria-describedby={errors.responseHours ? "target-response-error" : undefined}
                {...form.register("responseHours")}
              />
              <FieldError id="target-response-error">{errors.responseHours?.message}</FieldError>
            </Field>
            <Field data-invalid={errors.resolutionHours ? true : undefined}>
              <FieldLabel htmlFor="target-resolution">Resolution (hours)</FieldLabel>
              <Input
                id="target-resolution"
                inputMode="numeric"
                autoComplete="off"
                aria-invalid={errors.resolutionHours ? true : undefined}
                aria-describedby={errors.resolutionHours ? "target-resolution-error" : undefined}
                {...form.register("resolutionHours")}
              />
              <FieldError id="target-resolution-error">
                {errors.resolutionHours?.message}
              </FieldError>
            </Field>
          </div>
          <Controller
            control={form.control}
            name="businessHoursOnly"
            render={({ field }) => (
              <div className="flex items-start gap-2">
                <Checkbox
                  id="target-business"
                  checked={field.value}
                  aria-describedby="target-business-hint"
                  onCheckedChange={(checked) => {
                    field.onChange(checked);
                  }}
                />
                <div className="flex flex-col gap-0.5">
                  <Label htmlFor="target-business" className="text-sm">
                    Count working hours only
                  </Label>
                  <p id="target-business-hint" className="text-xs text-muted-foreground">
                    Monday to Saturday, 09:30 to 18:30: nine hours a day. Untick to count round the
                    clock.
                  </p>
                </div>
              </div>
            )}
          />
          <Field data-invalid={errors.effectiveFrom ? true : undefined}>
            <FieldLabel htmlFor="target-from">Starts on</FieldLabel>
            <Input
              id="target-from"
              type="date"
              min={today}
              className="sm:w-48"
              aria-invalid={errors.effectiveFrom ? true : undefined}
              aria-describedby={errors.effectiveFrom ? "target-from-error" : undefined}
              {...form.register("effectiveFrom")}
            />
            <FieldError id="target-from-error">{errors.effectiveFrom?.message}</FieldError>
          </Field>
        </FieldGroup>
        <Refusal refusal={refusal} />
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
          Set target
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ComplaintTargetsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the targets" className="grid gap-4 lg:grid-cols-3">
      {COMPLAINT_SEVERITIES.map((severity) => (
        <div key={severity} className="flex flex-col gap-3 rounded-xl border border-border p-4">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-20 w-full" />
        </div>
      ))}
    </div>
  );
}
