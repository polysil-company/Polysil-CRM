"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useSetTargets } from "@/features/targets/api/targets.mutations";
import { personTargetsQueryOptions } from "@/features/targets/api/targets.queries";
import {
  TARGET_METRICS,
  type PersonTargets,
  type SetTargetsRequest,
  type TargetMetric,
} from "@/features/targets/api/targets.schemas";
import { formatMeasure, isTargetMetric, METRIC_LABELS } from "@/features/targets/lib/target-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatMonth } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/targets/components/set-targets-dialog.tsx",
  dataId: "TGT-002",
});

type Draft = Readonly<Record<TargetMetric, string>>;

function draftOf(targets: PersonTargets["targets"]): Draft {
  return {
    // "300000.00" reads as "300000" in the field; paise stay when there are any.
    order_value: targets.orderValue?.replace(/\.00$/, "") ?? "",
    orders: targets.orders === null ? "" : String(targets.orders),
    leads_won: targets.leadsWon === null ? "" : String(targets.leadsWon),
    visits: targets.visits === null ? "" : String(targets.visits),
  };
}

/** Why a typed target won't do, before the backend checks it again; null when it reads right. */
function problemOf(metric: TargetMetric, text: string): string | null {
  if (text === "") return null;
  if (metric === "order_value") {
    return /^\d+(\.\d{1,2})?$/.test(text) ? null : "Rupees, with at most two decimal places.";
  }
  return /^\d+$/.test(text) ? null : "A whole number.";
}

/** The refusals PUT /targets names, in words. */
function refusalOf(error: unknown): string {
  if (isApiError(error)) {
    if (error.code === "not_your_team") {
      return "You can set targets only for the people below you.";
    }
    if (error.code === "month_closed") {
      return "This month has passed. Only an administrator changes a past month's targets.";
    }
    if (error.code === "user_inactive") return "This person is deactivated.";
    if (error.code === "no_targets") return "This person doesn't carry targets.";
  }
  return toUserFacingError(error).description;
}

/**
 * TGT-002 · Set a person's targets for the month: the four measures, of which only those that
 * change are sent. An emptied one is sent as 0, which clears it. Below, who set what and when.
 */
export function SetTargetsDialog({
  userId,
  name,
  month,
  pastMonth,
  onClose,
}: {
  userId: string;
  name: string;
  month: string;
  /** A month before this one: closed to all but administrators. */
  pastMonth: boolean;
  onClose: () => void;
}): React.JSX.Element {
  const query = useQuery(personTargetsQueryOptions(userId, month));
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>Targets for {name}</DialogTitle>
        <DialogDescription>
          {formatMonth(month)}. Leave a measure empty for no target.
        </DialogDescription>
      </DialogHeader>
      {query.status === "pending" ? (
        <DialogBody>
          <div role="status" aria-label="Loading targets" className="grid gap-3 sm:grid-cols-2">
            {TARGET_METRICS.map((metric) => (
              <Skeleton key={metric} className="h-16 w-full" />
            ))}
          </div>
        </DialogBody>
      ) : query.status === "error" ? (
        <DialogBody>
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        </DialogBody>
      ) : (
        <TargetsForm targets={query.data} pastMonth={pastMonth} onClose={onClose} />
      )}
    </div>
  );
}

function TargetsForm({
  targets,
  pastMonth,
  onClose,
}: {
  targets: PersonTargets;
  pastMonth: boolean;
  onClose: () => void;
}): React.JSX.Element {
  const mutation = useSetTargets();
  const idempotency = useIdempotencyKey();
  const initial = draftOf(targets.targets);
  const [draft, setDraft] = useState<Draft>(initial);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [server, setServer] = useState<Readonly<Record<string, string>>>({});

  const changed = TARGET_METRICS.filter((metric) => draft[metric].trim() !== initial[metric]);
  const problems: Partial<Record<TargetMetric, string>> = {};
  for (const metric of TARGET_METRICS) {
    const problem = problemOf(metric, draft[metric].trim());
    if (problem !== null) problems[metric] = problem;
  }

  const save = useAsyncAction({
    action: () => {
      const values: Partial<Record<TargetMetric, string | number>> = {};
      for (const metric of changed) {
        const text = draft[metric].trim();
        values[metric] =
          metric === "order_value" ? (text === "" ? "0" : text) : text === "" ? 0 : Number(text);
      }
      const body: SetTargetsRequest = {
        user_id: targets.user.id,
        month: targets.month,
        targets: values,
      };
      return mutation.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleSetTargets",
    dataId: "TGT-002",
    onSuccess: () => {
      idempotency.reset();
      toast.success(`Targets set for ${targets.user.name}`);
      onClose();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null && Object.keys(fields).some(isTargetMetric)) {
        const mapped: Record<string, string> = {};
        for (const [path, message] of Object.entries(fields)) {
          mapped[path.replace(/^targets\./, "")] = `The backend refused it: ${message}.`;
        }
        setServer(mapped);
        return;
      }
      setRefusal(refusalOf(error));
    },
  });

  return (
    <form
      noValidate
      aria-label={`Targets for ${targets.user.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        setServer({});
        if (Object.keys(problems).length > 0) return;
        if (changed.length === 0) {
          setRefusal("Nothing changed yet.");
          return;
        }
        void save.run();
      }}
    >
      <DialogBody className="flex flex-col gap-4">
        {pastMonth ? (
          <Notice tone="warning">
            This month has passed. Only an administrator changes a past month&apos;s targets.
          </Notice>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-2">
          {TARGET_METRICS.map((metric) => {
            const id = `target-${metric}`;
            const error = server[metric] ?? (shown ? problems[metric] : undefined);
            return (
              <Field key={metric} data-invalid={error === undefined ? undefined : true}>
                <FieldLabel htmlFor={id}>
                  {METRIC_LABELS[metric]}
                  {metric === "order_value" ? " (₹)" : ""}
                </FieldLabel>
                <Input
                  id={id}
                  inputMode={metric === "order_value" ? "decimal" : "numeric"}
                  className="tabular-nums"
                  value={draft[metric]}
                  placeholder="No target"
                  aria-invalid={error === undefined ? undefined : true}
                  aria-describedby={error === undefined ? undefined : `${id}-error`}
                  onChange={(event) => {
                    setDraft((current) => ({ ...current, [metric]: event.target.value }));
                    setServer({});
                  }}
                />
                {error === undefined && initial[metric] !== "" && draft[metric].trim() === "" ? (
                  <FieldDescription>Saving clears this target.</FieldDescription>
                ) : null}
                <FieldError id={`${id}-error`}>{error}</FieldError>
              </Field>
            );
          })}
        </div>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
        <History history={targets.history} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save targets
        </Button>
      </DialogFooter>
    </form>
  );
}

function History({ history }: { history: PersonTargets["history"] }): React.JSX.Element {
  return (
    <section aria-labelledby="targets-history" className="flex flex-col gap-2">
      <h3 id="targets-history" className="text-sm font-medium text-foreground">
        Changes to these targets
      </h3>
      {history.length === 0 ? (
        <p className="text-sm text-muted-foreground">None set for this month yet.</p>
      ) : (
        <ul className="flex flex-col gap-1.5 text-sm">
          {history.map((entry, index) => (
            <li key={`${entry.metric}-${entry.setAt}-${String(index)}`} className="text-foreground">
              {isTargetMetric(entry.metric) ? METRIC_LABELS[entry.metric] : entry.metric}{" "}
              {Number(entry.value) === 0
                ? "cleared"
                : `set to ${isTargetMetric(entry.metric) ? formatMeasure(entry.metric, entry.value) : String(entry.value)}`}
              <span className="text-muted-foreground">
                {entry.setBy === null ? "" : ` by ${entry.setBy}`},{" "}
                <RelativeDate value={entry.setAt} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
