"use client";

import { Add01Icon, Delete02Icon, Edit02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
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
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useReviseMaster } from "@/features/subsidy/api/subsidy-masters.mutations";
import { masterRowsQueryOptions } from "@/features/subsidy/api/subsidy-masters.queries";
import type {
  MasterKind,
  MasterRows,
  RevisionRow,
} from "@/features/subsidy/api/subsidy-masters.schemas";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import {
  changedRowIds,
  currentValue,
  editedValue,
  editProblem,
  effectiveFromProblem,
  sentValue,
  type EditableField,
  type Edits,
} from "@/features/subsidy/lib/master-revision";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import type { MasterConfig } from "./master-configs";

const log = createLogger({
  file: "features/subsidy/components/master-panel.tsx",
  dataId: "SUBS-012",
});

/**
 * SUBS-012 · One subsidy master's rows in force on a date, and — for whoever may edit masters —
 * a revision from a date: change the figures that need it (and, for crops, add some), and only
 * those rows are sent. Every row keeps its history; nothing is overwritten.
 */
export function MasterPanel<K extends MasterKind>({
  config,
  scheme,
  on,
  canEdit,
}: {
  config: MasterConfig<K>;
  /** The scheme whose rows these are, e.g. "GGRC". */
  scheme: string;
  on: string | null;
  canEdit: boolean;
}): React.JSX.Element {
  const query = useQuery(masterRowsQueryOptions(config.kind, scheme, on));
  const empty = query.data !== undefined && query.data.length === 0;
  const [revising, setRevising] = useState(false);

  return (
    <section aria-label={config.label} className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-prose text-sm text-muted-foreground">{config.description}</p>
        {canEdit && query.data !== undefined ? (
          <Button
            variant="outline"
            onClick={() => {
              setRevising(true);
            }}
          >
            <Icon icon={Edit02Icon} />
            {empty ? "Add rows from a date" : "Revise from a date"}
          </Button>
        ) : null}
      </div>
      <QueryView
        query={query}
        pending={<MasterTableSkeleton />}
        isEmpty={(rows) => rows.length === 0}
        empty={
          <EmptyState
            icon={Edit02Icon}
            title="Nothing in force on this date"
            description={
              canEdit
                ? "A new scheme starts empty: add its rows from a date."
                : "Choose a later date, or ask whoever keeps the scheme's masters."
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(rows) => <MasterTable config={config} rows={rows} />}
      </QueryView>

      <Dialog
        open={revising}
        onOpenChange={(open) => {
          if (!open) setRevising(false);
        }}
      >
        <DialogContent size="lg">
          {revising && query.data !== undefined ? (
            <RevisionForm
              config={config}
              scheme={scheme}
              rows={query.data}
              onClose={() => {
                setRevising(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function MasterTable<K extends MasterKind>({
  config,
  rows,
}: {
  config: MasterConfig<K>;
  rows: MasterRows[K];
}): React.JSX.Element {
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{config.label} in force</caption>
      <thead>
        <tr className="border-b border-border text-xs text-muted-foreground">
          {config.columns.map((column) => (
            <th
              key={column.key}
              scope="col"
              className={cn("py-2 pr-3 font-medium", column.numeric ? "text-right" : "text-left")}
            >
              {column.label}
            </th>
          ))}
          <th scope="col" className="hidden py-2 text-right font-medium sm:table-cell">
            Since
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className="border-b border-border align-top last:border-0">
            {config.columns.map((column) => (
              <td
                key={column.key}
                className={cn(
                  "py-2 pr-3 text-foreground",
                  column.numeric && "text-right tabular-nums",
                )}
              >
                {column.cell(row)}
              </td>
            ))}
            <td className="hidden py-2 text-right text-xs whitespace-nowrap text-muted-foreground sm:table-cell">
              {formatBusinessDay(row.effective_from)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MasterTableSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the master" className="flex flex-col gap-2">
      {Array.from({ length: 6 }, (_, index) => (
        <Skeleton key={index} className="h-9 w-full" />
      ))}
    </div>
  );
}

// ── the revision ──────────────────────────────────────────────────────────────────

interface NewRow {
  readonly key: string;
  readonly values: Readonly<Record<string, string>>;
}

function RevisionForm<K extends MasterKind>({
  config,
  scheme,
  rows,
  onClose,
}: {
  config: MasterConfig<K>;
  scheme: string;
  rows: MasterRows[K];
  onClose: () => void;
}): React.JSX.Element {
  const today = todayInIndia();
  const [effectiveFrom, setEffectiveFrom] = useState(today);
  const [edits, setEdits] = useState<Edits>({});
  const [added, setAdded] = useState<NewRow[]>([]);
  const [shown, setShown] = useState(false);
  const [serverProblems, setServerProblems] = useState<Readonly<Record<string, string>>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  const revise = useReviseMaster<K>();
  const idempotency = useIdempotencyKey();

  const changed = changedRowIds(rows, config.fields, edits);
  const changedRows = rows.filter((row) => changed.includes(row.id));
  // The order a revision sends rows in: changed ones, then new ones. A refusal's `rows[i]`
  // points into this list.
  const sentKeys = [...changedRows.map((row) => row.id), ...added.map((row) => row.key)];

  const problems: Record<string, string> = {};
  const dateProblem = effectiveFromProblem(effectiveFrom, today);
  if (dateProblem !== null) problems.effective_from = dateProblem;
  for (const row of changedRows) {
    for (const field of config.fields) {
      const problem = editProblem(field, editedValue(edits, row, field.key));
      if (problem !== null) problems[`${row.id}.${field.key}`] = problem;
    }
  }
  for (const row of added) {
    for (const field of config.adding?.fields ?? []) {
      const problem = editProblem(field, row.values[field.key] ?? "");
      if (problem !== null) problems[`${row.key}.${field.key}`] = problem;
    }
  }
  const visible: Readonly<Record<string, string>> = shown
    ? { ...serverProblems, ...problems }
    : serverProblems;
  const nothing = sentKeys.length === 0;

  const submit = useAsyncAction({
    action: () => {
      const revised: RevisionRow<K>[] = changedRows.map((row) =>
        config.toRevision(row, (key) => {
          const field = config.fields.find((item) => item.key === key);
          return field === undefined ? null : sentValue(field, editedValue(edits, row, key));
        }),
      );
      const adding = config.adding;
      const fresh: RevisionRow<K>[] =
        adding === undefined
          ? []
          : added.map((row) =>
              adding.build((key) => {
                const field = adding.fields.find((item) => item.key === key);
                return field === undefined ? null : sentValue(field, row.values[key] ?? "");
              }),
            );
      const body = {
        scheme,
        effective_from: effectiveFrom,
        rows: [...revised, ...fresh],
      };
      return revise.mutateAsync({
        kind: config.kind,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleReviseMaster",
    dataId: "SUBS-012",
    onSuccess: (result) => {
      idempotency.reset();
      toast.success(`${config.label} revised`, {
        description: `${String(result.inserted)} row${result.inserted === 1 ? "" : "s"} from ${formatBusinessDay(result.effectiveFrom)}; earlier calculations keep the old figures.`,
      });
      onClose();
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      // `rows[i]` names the i-th row sent; put it on that row.
      const mapped: Record<string, string> = {};
      for (const [path, message] of Object.entries(fields)) {
        const match = /^rows\[(\d+)\]/.exec(path);
        const key = match === null ? undefined : sentKeys[Number(match[1])];
        mapped[key === undefined ? path : `${key}.row`] = message;
      }
      setServerProblems(mapped);
      if (isApiError(error) && error.code === "later_revision_exists") {
        setRefusal("A later revision exists for a marked row. Revise from after it.");
      } else if (isApiError(error) && error.code === "revision_on_start_date") {
        setRefusal("A marked row already has a revision starting that day. Choose another date.");
      } else if (Object.keys(fields).length > 0) {
        setRefusal("The marked rows need correcting.");
      } else {
        setRefusal(toUserFacingError(error).title);
      }
    },
  });

  const setEdit = (rowId: string, key: string, value: string): void => {
    setEdits((current) => ({ ...current, [rowId]: { ...current[rowId], [key]: value } }));
    setServerProblems({});
  };

  return (
    <form
      noValidate
      aria-label={`Revise ${config.label.toLowerCase()}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (nothing || Object.keys(problems).length > 0) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>
          {rows.length === 0 ? "Add" : "Revise"} {config.label.toLowerCase()} · {scheme}
        </DialogTitle>
        <DialogDescription>
          Change the figures that need it. Only those rows are sent; each starts on the date below,
          and calculations made before it keep the old figures.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field
          data-invalid={visible.effective_from === undefined ? undefined : true}
          className="sm:max-w-xs"
        >
          <FieldLabel htmlFor="revision-from">Starts on</FieldLabel>
          <Input
            id="revision-from"
            type="date"
            min={today}
            value={effectiveFrom}
            aria-invalid={visible.effective_from === undefined ? undefined : true}
            aria-describedby={
              visible.effective_from === undefined ? undefined : "revision-from-error"
            }
            onChange={(event) => {
              setEffectiveFrom(event.target.value);
            }}
          />
          <FieldError id="revision-from-error">{visible.effective_from}</FieldError>
        </Field>

        <ul aria-label="Rows" className="flex flex-col divide-y divide-border">
          {rows.map((row) => {
            const rowProblem = visible[`${row.id}.row`];
            const isChanged = changed.includes(row.id);
            return (
              <li
                key={row.id}
                aria-label={config.rowName(row)}
                className={cn(
                  "flex flex-col gap-2 py-3",
                  isChanged && "-mx-2 rounded-md bg-muted px-2",
                )}
              >
                <p className="text-sm font-medium text-foreground">
                  {config.rowName(row)}
                  {isChanged ? (
                    <span className="ml-2 text-xs font-normal text-primary">Changed</span>
                  ) : null}
                </p>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  {config.fields.map((field) => {
                    const id = `rev-${row.id}-${field.key}`;
                    const error = visible[`${row.id}.${field.key}`];
                    return (
                      <div key={field.key} className="flex min-w-0 flex-col gap-1">
                        <label htmlFor={id} className="text-xs text-muted-foreground">
                          {field.label}
                          {field.required ? "" : " (optional)"}
                        </label>
                        <Input
                          id={id}
                          inputMode={field.places === undefined ? undefined : "decimal"}
                          autoComplete="off"
                          className={field.places === undefined ? undefined : "tabular-nums"}
                          value={editedValue(edits, row, field.key)}
                          placeholder={currentValue(row, field.key) === "" ? "None" : undefined}
                          aria-invalid={error === undefined ? undefined : true}
                          aria-describedby={error === undefined ? undefined : `${id}-error`}
                          onChange={(event) => {
                            setEdit(row.id, field.key, event.target.value);
                          }}
                        />
                        {error === undefined ? null : (
                          <p id={`${id}-error`} className="text-xs text-danger">
                            {error}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
                {rowProblem === undefined ? null : (
                  <p role="alert" className="text-xs text-danger">
                    {rowProblem}
                  </p>
                )}
              </li>
            );
          })}
        </ul>

        {config.adding === undefined ? null : (
          <AddedRows adding={config.adding} rows={added} problems={visible} onChange={setAdded} />
        )}

        {shown && nothing ? (
          <p role="alert" className="text-sm text-danger">
            Nothing has changed yet: change a figure
            {config.adding === undefined ? "" : " or add a row"}.
          </p>
        ) : null}
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <span className="mr-auto text-xs text-muted-foreground" aria-live="polite">
          {sentKeys.length === 0
            ? "No rows changed"
            : `${String(sentKeys.length)} row${sentKeys.length === 1 ? "" : "s"} to send`}
        </span>
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
          Save the revision
        </Button>
      </DialogFooter>
    </form>
  );
}

function AddedRows<K extends MasterKind>({
  adding,
  rows,
  problems,
  onChange,
}: {
  adding: NonNullable<MasterConfig<K>["adding"]>;
  rows: readonly NewRow[];
  problems: Readonly<Record<string, string>>;
  onChange: (rows: NewRow[]) => void;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-2">
      {rows.length > 0 ? (
        <ul aria-label="New rows" className="flex flex-col gap-2">
          {rows.map((row, index) => (
            <li
              key={row.key}
              aria-label={`New row ${String(index + 1)}`}
              className="flex flex-col gap-2 rounded-lg border border-dashed border-border p-3"
            >
              <div className="flex items-end gap-2">
                <div className="grid flex-1 gap-2 sm:grid-cols-2">
                  {adding.fields.map((field) => {
                    const id = `new-${row.key}-${field.key}`;
                    const error = problems[`${row.key}.${field.key}`];
                    return (
                      <div key={field.key} className="flex min-w-0 flex-col gap-1">
                        <label htmlFor={id} className="text-xs text-muted-foreground">
                          {field.label}
                        </label>
                        <MasterFieldInput
                          id={id}
                          field={field}
                          value={row.values[field.key] ?? ""}
                          error={error}
                          onChange={(next) => {
                            onChange(
                              rows.map((item) =>
                                item.key === row.key
                                  ? { ...item, values: { ...item.values, [field.key]: next } }
                                  : item,
                              ),
                            );
                          }}
                        />
                        {error === undefined ? null : (
                          <p id={`${id}-error`} className="text-xs text-danger">
                            {error}
                          </p>
                        )}
                      </div>
                    );
                  })}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-md"
                  aria-label={`Remove new row ${String(index + 1)}`}
                  onClick={() => {
                    onChange(rows.filter((item) => item.key !== row.key));
                  }}
                >
                  <Icon icon={Delete02Icon} />
                </Button>
              </div>
              {problems[`${row.key}.row`] === undefined ? null : (
                <p role="alert" className="text-xs text-danger">
                  {problems[`${row.key}.row`]}
                </p>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="self-start"
        onClick={() => {
          onChange([...rows, { key: createRequestId(), values: {} }]);
        }}
      >
        <Icon icon={Add01Icon} />
        {adding.label}
      </Button>
    </div>
  );
}

/** One field of a new row: a choice when the field has options, typed text otherwise. */
function MasterFieldInput({
  id,
  field,
  value,
  error,
  onChange,
}: {
  id: string;
  field: EditableField;
  value: string;
  error: string | undefined;
  onChange: (value: string) => void;
}): React.JSX.Element {
  const aria = {
    "aria-invalid": error === undefined ? undefined : true,
    "aria-describedby": error === undefined ? undefined : `${id}-error`,
  } as const;
  if (field.options !== undefined) {
    const options = field.options;
    return (
      <Select
        items={options}
        value={value === "" ? null : value}
        onValueChange={(next) => {
          onChange(typeof next === "string" ? next : "");
        }}
      >
        <SelectTrigger id={id} className="w-full" {...aria}>
          <SelectValue placeholder={field.required ? "Choose" : "None"} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }
  return (
    <Input
      id={id}
      inputMode={field.places !== undefined || field.integer === true ? "decimal" : undefined}
      autoComplete="off"
      value={value}
      onChange={(event) => {
        onChange(event.target.value);
      }}
      {...aria}
    />
  );
}
