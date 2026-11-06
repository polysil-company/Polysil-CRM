"use client";

import { Copy01Icon, GridTableIcon, PlusSignIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCreateMatrix } from "@/features/subsidy/api/subsidy-masters.mutations";
import {
  quantityMatricesQueryOptions,
  unitCostMatricesQueryOptions,
} from "@/features/subsidy/api/subsidy-masters.queries";
import type {
  MatrixRequest,
  QuantityMatrix,
  UnitCostMatrix,
} from "@/features/subsidy/api/subsidy-masters.schemas";
import { SYSTEM_TYPES, type SystemType } from "@/features/subsidy/api/subsidy.schemas";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { effectiveFromProblem } from "@/features/subsidy/lib/master-revision";
import {
  parseQuantityGrid,
  parseUnitCostGrid,
  quantityGridOf,
  unitCostGridOf,
} from "@/features/subsidy/lib/matrix-grid";
import { SYSTEM_LABELS } from "@/features/subsidy/lib/subsidy-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/subsidy/components/matrix-panel.tsx",
  dataId: "SUBS-013",
});

type AnyMatrix =
  | { readonly kind: "unit-cost"; readonly matrix: UnitCostMatrix }
  | { readonly kind: "quantity"; readonly matrix: QuantityMatrix };

function titleOf(item: AnyMatrix): string {
  const system = SYSTEM_LABELS[item.matrix.system_type];
  if (item.kind === "quantity") return `${system} quantities`;
  return `${system} · ${item.matrix.variant === "seven_year" ? "Seven-year" : "Regular"}`;
}

function gridOf(item: AnyMatrix): string {
  return item.kind === "unit-cost" ? unitCostGridOf(item.matrix) : quantityGridOf(item.matrix);
}

/** A grid as rows of cells, for the table: the first row the areas. */
function tableOf(item: AnyMatrix): { header: string[]; rows: string[][] } {
  const [header = [], ...rows] = gridOf(item)
    .split("\n")
    .map((line) => line.split("\t"));
  return { header, rows };
}

/**
 * SUBS-013 · The unit-cost (Jantri) or quantity matrices in force on a date, each as the grid
 * the scheme prints. Anyone may copy one as a grid for Excel; whoever may edit masters starts a
 * new one from a date by pasting its grid back. A matrix's cells never change: a new matrix
 * ends the one in force.
 */
export function MatrixPanel({
  kind,
  scheme,
  on,
  canEdit,
}: {
  kind: "unit-cost" | "quantity";
  /** The scheme whose matrices these are, e.g. "GGRC". */
  scheme: string;
  on: string | null;
  canEdit: boolean;
}): React.JSX.Element {
  const unitCosts = useQuery({
    ...unitCostMatricesQueryOptions(scheme, on),
    enabled: kind === "unit-cost",
  });
  const quantities = useQuery({
    ...quantityMatricesQueryOptions(scheme, on),
    enabled: kind === "quantity",
  });
  const [starting, setStarting] = useState<MatrixTarget | null>(null);
  const items: AnyMatrix[] =
    kind === "unit-cost"
      ? (unitCosts.data ?? []).map((matrix) => ({ kind: "unit-cost", matrix }))
      : (quantities.data ?? []).map((matrix) => ({ kind: "quantity", matrix }));
  const description =
    kind === "unit-cost"
      ? "The unit cost the scheme allows, by lateral spacing and area. The calculation reads between rows and columns."
      : "Sprinkler's quantities of each component, by area.";
  const loaded = kind === "unit-cost" ? unitCosts.isSuccess : quantities.isSuccess;

  const body = (list: AnyMatrix[]): React.JSX.Element => (
    <div className="grid gap-4 xl:grid-cols-2">
      {list.map((item) => (
        <MatrixCard
          key={item.matrix.id}
          item={item}
          canEdit={canEdit}
          onReplace={() => {
            setStarting(targetOf(item));
          }}
        />
      ))}
    </div>
  );
  const empty = (
    <EmptyState
      icon={GridTableIcon}
      title="No matrix in force on this date"
      description={
        canEdit
          ? "A new scheme starts without one: start a matrix from a date."
          : "Choose a later date, or ask whoever keeps the scheme's masters."
      }
      className="rounded-xl border border-dashed border-border"
    />
  );

  return (
    <section
      aria-label={kind === "unit-cost" ? "Unit costs" : "Quantities"}
      className="flex flex-col gap-4"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-prose text-sm text-muted-foreground">{description}</p>
        {canEdit && loaded ? (
          <Button
            variant="outline"
            onClick={() => {
              setStarting(
                kind === "unit-cost"
                  ? { kind, system: "drip", variant: "regular", dimensionality: 2 }
                  : { kind, system: "sprinkler" },
              );
            }}
          >
            <Icon icon={PlusSignIcon} />
            New matrix
          </Button>
        ) : null}
      </div>
      {kind === "unit-cost" ? (
        <QueryView
          query={unitCosts}
          pending={<MatrixSkeleton />}
          isEmpty={(rows) => rows.length === 0}
          empty={empty}
        >
          {(rows) => body(rows.map((matrix) => ({ kind: "unit-cost", matrix })))}
        </QueryView>
      ) : (
        <QueryView
          query={quantities}
          pending={<MatrixSkeleton />}
          isEmpty={(rows) => rows.length === 0}
          empty={empty}
        >
          {(rows) => body(rows.map((matrix) => ({ kind: "quantity", matrix })))}
        </QueryView>
      )}

      <Dialog
        open={starting !== null}
        onOpenChange={(open) => {
          if (!open) setStarting(null);
        }}
      >
        <DialogContent size="lg">
          {starting === null ? null : (
            <NewMatrixForm
              initial={starting}
              scheme={scheme}
              inForce={items}
              onClose={() => {
                setStarting(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function MatrixCard({
  item,
  canEdit,
  onReplace,
}: {
  item: AnyMatrix;
  canEdit: boolean;
  onReplace: () => void;
}): React.JSX.Element {
  const clipboard = useCopyToClipboard();
  const { header, rows } = tableOf(item);
  const title = titleOf(item);
  return (
    <Card aria-label={title}>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>{title}</CardTitle>
          <CardDescription>
            Since {formatBusinessDay(item.matrix.effective_from)}
            {item.matrix.source === null ? "" : ` · ${item.matrix.source}`}
          </CardDescription>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              void clipboard.copy(gridOf(item)).then((ok) => {
                if (!ok)
                  toast.error("The grid couldn't be copied", {
                    description: "Select it and copy instead.",
                  });
              });
            }}
          >
            <Icon icon={Copy01Icon} />
            {clipboard.copied ? "Copied" : "Copy as grid"}
          </Button>
          {canEdit ? (
            <Button variant="outline" size="sm" onClick={onReplace}>
              <Icon icon={PlusSignIcon} />
              New matrix
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        {/* The grid can be wider than a phone; the region scrolls and takes focus to do so. */}
        <div
          role="region"
          aria-label={`${title} grid`}
          // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be reachable by keyboard (WCAG 2.1.1)
          tabIndex={0}
          className="overflow-x-auto focus-ring-inset"
        >
          <table className="w-full min-w-max text-xs">
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                {header.map((cell, index) => (
                  <th
                    key={`${String(index)}-${cell}`}
                    scope="col"
                    className={
                      index === 0
                        ? "py-1.5 pr-3 text-left font-medium"
                        : "py-1.5 pl-3 text-right font-medium"
                    }
                  >
                    {index === 0 ? cell : `${cell} Ha`}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row[0]} className="border-b border-border last:border-0">
                  {row.map((cell, index) =>
                    index === 0 ? (
                      <th
                        key="label"
                        scope="row"
                        className="py-1.5 pr-3 text-left font-normal text-foreground"
                      >
                        {item.kind === "unit-cost" && cell !== "Unit cost" ? `${cell} m` : cell}
                      </th>
                    ) : (
                      <td
                        key={String(index)}
                        className="py-1.5 pl-3 text-right text-foreground tabular-nums"
                      >
                        {cell}
                      </td>
                    ),
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function MatrixSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the matrices" className="grid gap-4 xl:grid-cols-2">
      <Skeleton className="h-56 w-full rounded-xl" />
      <Skeleton className="h-56 w-full rounded-xl" />
    </div>
  );
}

// ── a new matrix ──────────────────────────────────────────────────────────────────

/** Which matrix a new one replaces: its system, and for unit costs its variant and shape. */
type MatrixTarget =
  | {
      readonly kind: "unit-cost";
      readonly system: SystemType;
      readonly variant: "regular" | "seven_year";
      readonly dimensionality: 1 | 2;
    }
  | { readonly kind: "quantity"; readonly system: SystemType };

function targetOf(item: AnyMatrix): MatrixTarget {
  return item.kind === "unit-cost"
    ? {
        kind: "unit-cost",
        system: item.matrix.system_type,
        variant: item.matrix.variant,
        dimensionality: item.matrix.dimensionality,
      }
    : { kind: "quantity", system: item.matrix.system_type };
}

/** The matrix in force for a target, to start the grid from; null when there is none. */
function baseFor(target: MatrixTarget, inForce: readonly AnyMatrix[]): AnyMatrix | null {
  return (
    inForce.find((item) =>
      item.kind === "unit-cost" && target.kind === "unit-cost"
        ? item.matrix.system_type === target.system && item.matrix.variant === target.variant
        : item.kind === "quantity" && target.kind === "quantity"
          ? item.matrix.system_type === target.system
          : false,
    ) ?? null
  );
}

/** An empty grid's first row, so the shape is clear before anything is pasted. */
function blankGrid(target: MatrixTarget): string {
  if (target.kind === "quantity") return "Component \\ Area\t0.400\t1.000\t2.000\t5.000\n";
  return target.dimensionality === 2
    ? "Spacing \\ Area\t0.400\t1.000\t2.000\t5.000\n"
    : "Area\t0.400\t1.000\t2.000\t5.000\nUnit cost\t\t\t\t\n";
}

function titleOfTarget(target: MatrixTarget): string {
  const system = SYSTEM_LABELS[target.system];
  if (target.kind === "quantity") return `${system} quantities`;
  return `${system} · ${target.variant === "seven_year" ? "Seven-year" : "Regular"}`;
}

const SYSTEM_ITEMS = SYSTEM_TYPES.map((value) => ({ value, label: SYSTEM_LABELS[value] }));

function NewMatrixForm({
  initial,
  scheme,
  inForce,
  onClose,
}: {
  initial: MatrixTarget;
  scheme: string;
  inForce: readonly AnyMatrix[];
  onClose: () => void;
}): React.JSX.Element {
  const today = todayInIndia();
  const [target, setTarget] = useState<MatrixTarget>(initial);
  const [effectiveFrom, setEffectiveFrom] = useState(today);
  const [source, setSource] = useState("");
  const base = baseFor(target, inForce);
  const [grid, setGrid] = useState(() => {
    const first = baseFor(initial, inForce);
    return first === null ? blankGrid(initial) : gridOf(first);
  });
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const create = useCreateMatrix();
  const idempotency = useIdempotencyKey();
  const title = titleOfTarget(target);

  /** A new target starts its grid from the matrix in force for it, or blank. */
  const retarget = (next: MatrixTarget): void => {
    setTarget(next);
    const nextBase = baseFor(next, inForce);
    setGrid(nextBase === null ? blankGrid(next) : gridOf(nextBase));
  };

  const parsed =
    target.kind === "unit-cost"
      ? parseUnitCostGrid(grid, target.dimensionality)
      : parseQuantityGrid(grid);
  const problems: Record<string, string> = {};
  const dateProblem = effectiveFromProblem(effectiveFrom, today);
  if (dateProblem !== null) problems.effective_from = dateProblem;
  if (source.trim() === "") {
    problems.source = "Say where the figures come from, e.g. the scheme's circular.";
  }
  if (parsed.problems.length > 0) problems.grid = "The grid needs correcting.";
  const visible = shown ? problems : {};

  const submit = useAsyncAction({
    action: () => {
      const request: MatrixRequest =
        target.kind === "unit-cost"
          ? {
              kind: "unit-cost-matrices",
              body: {
                scheme,
                system_type: target.system,
                variant: target.variant,
                dimensionality: target.dimensionality,
                effective_from: effectiveFrom,
                source: source.trim(),
                unit_cost_cells: parseUnitCostGrid(grid, target.dimensionality).cells,
              },
            }
          : {
              kind: "quantity-matrices",
              body: {
                scheme,
                system_type: target.system,
                effective_from: effectiveFrom,
                source: source.trim(),
                quantity_cells: parseQuantityGrid(grid).cells,
              },
            };
      return create.mutateAsync({ request, idempotencyKey: idempotency.keyFor(request) });
    },
    logger: log,
    fn: "handleCreateMatrix",
    dataId: "SUBS-013",
    onSuccess: (result) => {
      idempotency.reset();
      toast.success(`New ${title.toLowerCase()} matrix saved`, {
        description: `${String(result.inserted)} cells from ${formatBusinessDay(result.effectiveFrom)}; the one in force ends that day.`,
      });
      onClose();
    },
    onError: (error) => {
      if (
        isApiError(error) &&
        (error.code === "later_revision_exists" || error.code === "revision_on_start_date")
      ) {
        setRefusal(
          error.code === "revision_on_start_date"
            ? "A matrix already starts that day. Choose another date."
            : "A later matrix already exists. Start this one after it.",
        );
        return;
      }
      const fields = readFieldErrors(error);
      setRefusal(
        fields === null
          ? toUserFacingError(error).title
          : Object.entries(fields)
              .map(([path, message]) => `${path}: ${message}`)
              .join(" · "),
      );
    },
  });

  return (
    <form
      noValidate
      aria-label="New matrix"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (Object.keys(problems).length > 0) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>
          New matrix: {title} · {scheme}
        </DialogTitle>
        <DialogDescription>
          Paste the whole grid from Excel; every cell is saved.{" "}
          {base === null
            ? "No matrix is in force for this yet."
            : "The matrix in force ends on the start date; calculations made before it keep the old figures."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field>
            <FieldLabel htmlFor="matrix-system">System</FieldLabel>
            <Select
              items={SYSTEM_ITEMS}
              value={target.system}
              onValueChange={(next) => {
                const system = SYSTEM_TYPES.find((item) => item === next);
                if (system !== undefined) retarget({ ...target, system });
              }}
            >
              <SelectTrigger id="matrix-system" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SYSTEM_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          {target.kind === "unit-cost" ? (
            <>
              <Field>
                <FieldLabel htmlFor="matrix-variant">Variant</FieldLabel>
                <Select
                  items={VARIANT_ITEMS}
                  value={target.variant}
                  onValueChange={(next) => {
                    retarget({
                      ...target,
                      variant: next === "seven_year" ? "seven_year" : "regular",
                    });
                  }}
                >
                  <SelectTrigger id="matrix-variant" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {VARIANT_ITEMS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="matrix-shape">Shape</FieldLabel>
                <Select
                  items={SHAPE_ITEMS}
                  value={String(target.dimensionality)}
                  onValueChange={(next) => {
                    retarget({ ...target, dimensionality: next === "1" ? 1 : 2 });
                  }}
                >
                  <SelectTrigger id="matrix-shape" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SHAPE_ITEMS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </>
          ) : null}
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={visible.effective_from === undefined ? undefined : true}>
            <FieldLabel htmlFor="matrix-from">Starts on</FieldLabel>
            <Input
              id="matrix-from"
              type="date"
              min={today}
              value={effectiveFrom}
              aria-invalid={visible.effective_from === undefined ? undefined : true}
              aria-describedby={
                visible.effective_from === undefined ? undefined : "matrix-from-error"
              }
              onChange={(event) => {
                setEffectiveFrom(event.target.value);
              }}
            />
            <FieldError id="matrix-from-error">{visible.effective_from}</FieldError>
          </Field>
          <Field data-invalid={visible.source === undefined ? undefined : true}>
            <FieldLabel htmlFor="matrix-source">Source</FieldLabel>
            <Input
              id="matrix-source"
              maxLength={200}
              placeholder="The scheme's circular 12/2027"
              value={source}
              aria-invalid={visible.source === undefined ? undefined : true}
              aria-describedby={visible.source === undefined ? undefined : "matrix-source-error"}
              onChange={(event) => {
                setSource(event.target.value);
              }}
            />
            <FieldError id="matrix-source-error">{visible.source}</FieldError>
          </Field>
        </div>
        <Field data-invalid={visible.grid === undefined ? undefined : true}>
          <FieldLabel htmlFor="matrix-grid">The grid</FieldLabel>
          <Textarea
            id="matrix-grid"
            spellCheck={false}
            className="min-h-48 font-mono text-xs"
            value={grid}
            aria-invalid={visible.grid === undefined ? undefined : true}
            aria-describedby="matrix-grid-status"
            onChange={(event) => {
              setGrid(event.target.value);
            }}
          />
          <FieldDescription id="matrix-grid-status">
            {parsed.problems.length === 0
              ? `${String(parsed.cells.length)} cells read.`
              : "The first row holds the areas; each row after it starts with its " +
                (target.kind === "unit-cost"
                  ? target.dimensionality === 2
                    ? "lateral spacing."
                    : "label, then the unit costs."
                  : "component code.")}
          </FieldDescription>
          {parsed.problems.length > 0 && shown ? (
            <ul
              aria-label="Problems in the grid"
              className="flex list-disc flex-col gap-0.5 pl-4 text-xs text-danger"
            >
              {parsed.problems.slice(0, 8).map((problem) => (
                <li key={problem}>{problem}</li>
              ))}
              {parsed.problems.length > 8 ? (
                <li>…and {String(parsed.problems.length - 8)} more.</li>
              ) : null}
            </ul>
          ) : null}
        </Field>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
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
          Save the matrix
        </Button>
      </DialogFooter>
    </form>
  );
}

const VARIANT_ITEMS = [
  { value: "regular", label: "Regular" },
  { value: "seven_year", label: "Seven-year" },
] as const;

const SHAPE_ITEMS = [
  { value: "2", label: "Spacing by area" },
  { value: "1", label: "Area only" },
] as const;
