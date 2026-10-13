"use client";

import {
  ArrowLeft01Icon,
  CheckmarkCircle02Icon,
  FileImportIcon,
  FileSpreadsheetIcon,
} from "@hugeicons/core-free-icons";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";

import { Badge } from "@/components/ui/badge";
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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { discardImport } from "@/features/imports/api/imports.api";
import {
  useCheckImport,
  useCommitImport,
  useUploadImport,
} from "@/features/imports/api/imports.mutations";
import {
  IMPORT_MODES,
  type ImportBatch,
  type ImportCheck,
  type ImportCommitResult,
  type ImportField,
  type ImportKind,
  type ImportLine,
  type ImportMapping,
  type ImportMode,
} from "@/features/imports/api/imports.schemas";
import { importRefusal, type ImportRefusal } from "@/features/imports/lib/import-refusals";
import { useAsyncAction, type AsyncActionState } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { createRequestId } from "@/lib/api/request-id";
import { formatCount, formatFileSize } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/imports/components/import-dialog.tsx",
  dataId: "MSTR-007",
});

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = ".xlsx,.csv";
/** The Select's "don't import this column" choice; a Select item needs a string value. */
const SKIP = "skip";

const MODE_TEXT: Readonly<Record<ImportMode, { label: string; help: string }>> = {
  replace: { label: "Replace", help: "The file becomes the whole list." },
  merge: { label: "Merge", help: "Rates for products not in the file stay as they are." },
};

/** What the dialog says about the rows it imports. */
export interface ImportNoun {
  /** "rate", "partner", "line" */
  readonly one: string;
  /** "rates", "partners", "lines" */
  readonly many: string;
}

export interface ImportDialogProps {
  readonly kind: ImportKind;
  /** The draft price list, for `price_list_items`. */
  readonly targetId?: string;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly title: string;
  readonly description: string;
  readonly noun: ImportNoun;
  /** Partners and rates: the import is saved. Refresh what shows them. */
  readonly onCommitted?: (result: ImportCommitResult) => void;
  /** Lines: the good rows, for the line editor to add. There is no commit. */
  readonly onLines?: (lines: readonly ImportLine[]) => void;
  /** Lines: the button that adds them, "Add to quotation". */
  readonly linesAction?: string;
}

/**
 * MSTR-007 · Import from Excel, in three steps (handover `excel-import.md`): upload a `.xlsx` or
 * `.csv`; match each of its columns to a field (the backend suggests a match); review the
 * counts, every bad row and the first good ones, then import — all of it, or the good rows
 * only. A dialog closed before importing discards its upload.
 */
export function ImportDialog(props: ImportDialogProps): React.JSX.Element {
  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent size="lg">
        {props.open ? (
          <ImportFlow
            {...props}
            onClose={() => {
              props.onOpenChange(false);
            }}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

type Step =
  | { readonly kind: "upload" }
  | { readonly kind: "match"; readonly batch: ImportBatch }
  | { readonly kind: "review"; readonly batch: ImportBatch; readonly check: ImportCheck }
  | { readonly kind: "done"; readonly result: ImportCommitResult };

/** The picked file, and the sheet and header row to read it from. */
interface Source {
  readonly file: File;
  readonly sheet?: string | undefined;
  readonly headerRow?: number | undefined;
}

function ImportFlow({
  kind,
  targetId,
  title,
  description,
  noun,
  onCommitted,
  onLines,
  linesAction,
  onClose,
}: ImportDialogProps & { onClose: () => void }): React.JSX.Element {
  const [step, setStep] = useState<Step>({ kind: "upload" });
  const [source, setSource] = useState<Source | null>(null);
  const [mapping, setMapping] = useState<ImportMapping>({});
  const [mode, setMode] = useState<ImportMode>("replace");
  const [refusal, setRefusal] = useState<ImportRefusal | null>(null);
  const upload = useUploadImport();
  const check = useCheckImport();
  const commit = useCommitImport();
  const uploadKey = useIdempotencyKey();
  const checkKey = useIdempotencyKey();
  const commitKey = useIdempotencyKey();

  // An upload not imported when the dialog closes is discarded, as the backend asks.
  const pending = useRef<string | null>(null);
  useEffect(() => {
    return () => {
      const batchId = pending.current;
      if (batchId === null) return;
      pending.current = null;
      void log.trace("discardOnClose", () =>
        discardImport({ batchId, idempotencyKey: createRequestId() }).catch(() => undefined),
      );
    };
  }, []);

  const replaceBatch = (next: ImportBatch): void => {
    const previous = pending.current;
    if (previous !== null && previous !== next.id) {
      void discardImport({ batchId: previous, idempotencyKey: createRequestId() }).catch(
        () => undefined,
      );
    }
    pending.current = next.id;
  };

  const runUpload = useAsyncAction({
    action: (next: Source) =>
      upload.mutateAsync({
        kind,
        file: next.file,
        targetId,
        sheet: next.sheet,
        headerRow: next.headerRow,
        idempotencyKey: uploadKey.keyFor({
          name: next.file.name,
          size: next.file.size,
          modified: next.file.lastModified,
          sheet: next.sheet ?? null,
          headerRow: next.headerRow ?? null,
        }),
      }),
    logger: log,
    fn: "handleUploadImport",
    dataId: "MSTR-007",
    onSuccess: (batch) => {
      uploadKey.reset();
      replaceBatch(batch);
      setMapping(batch.suggestedMapping);
      setStep({ kind: "match", batch });
    },
    onError: (error) => {
      setRefusal(importRefusal(error));
    },
  });

  const runCheck = useAsyncAction({
    action: (batch: ImportBatch) => {
      const body = {
        mapping,
        ...(kind === "price_list_items" ? { options: { mode } } : {}),
      };
      return check.mutateAsync({
        batchId: batch.id,
        body,
        idempotencyKey: checkKey.keyFor({ batch: batch.id, ...body }),
      });
    },
    logger: log,
    fn: "handleCheckImport",
    dataId: "MSTR-007",
    onSuccess: (result) => {
      checkKey.reset();
      if (step.kind === "match") setStep({ kind: "review", batch: step.batch, check: result });
    },
    onError: (error) => {
      const read = importRefusal(error);
      setRefusal(read);
      if (read.finished) setStep({ kind: "upload" });
    },
  });

  const runCommit = useAsyncAction({
    action: ({ batch, skipInvalid }: { batch: ImportBatch; skipInvalid: boolean }) =>
      commit.mutateAsync({
        batchId: batch.id,
        skipInvalid,
        idempotencyKey: commitKey.keyFor({ batch: batch.id, skipInvalid }),
      }),
    logger: log,
    fn: "handleCommitImport",
    dataId: "MSTR-007",
    onSuccess: (result) => {
      commitKey.reset();
      pending.current = null;
      onCommitted?.(result);
      setStep({ kind: "done", result });
    },
    onError: (error) => {
      const read = importRefusal(error);
      setRefusal(read);
      if (read.finished) {
        pending.current = null;
        setStep({ kind: "upload" });
      }
    },
  });

  const busy = runUpload.isBusy || runCheck.isBusy || runCommit.isBusy;
  const back = (batch: ImportBatch): void => {
    setRefusal(null);
    setStep({ kind: "match", batch });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        <DialogDescription>{description}</DialogDescription>
        <StepTrail step={step.kind} />
      </DialogHeader>
      <DialogBody>
        {step.kind === "upload" ? (
          <UploadStep
            file={source?.file ?? null}
            onFile={(file) => {
              setRefusal(null);
              setSource(file === null ? null : { file });
            }}
          />
        ) : null}
        {step.kind === "match" ? (
          <MatchStep
            batch={step.batch}
            mapping={mapping}
            onMapping={setMapping}
            mapProblems={refusal?.mapping ?? {}}
            mode={kind === "price_list_items" ? mode : null}
            onMode={setMode}
            busy={busy}
            onReread={(sheet, headerRow) => {
              if (source === null) return;
              const next = { file: source.file, sheet, headerRow };
              setSource(next);
              setRefusal(null);
              void runUpload.run(next);
            }}
          />
        ) : null}
        {step.kind === "review" ? (
          <ReviewStep batch={step.batch} check={step.check} mapping={mapping} noun={noun} />
        ) : null}
        {step.kind === "done" ? <DoneStep result={step.result} noun={noun} /> : null}
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        {step.kind === "upload" ? (
          <>
            <DialogClose render={<Button type="button" variant="outline" disabled={busy} />}>
              Cancel
            </DialogClose>
            <Button
              disabled={source === null || source.file.size > MAX_BYTES}
              state={runUpload.state}
              loadingLabel="Reading the file…"
              successLabel="Read"
              errorLabel="Not read"
              onClick={() => {
                if (source === null) return;
                setRefusal(null);
                void runUpload.run(source);
              }}
            >
              Upload
            </Button>
          </>
        ) : null}
        {step.kind === "match" ? (
          <>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setRefusal(null);
                setStep({ kind: "upload" });
              }}
            >
              <Icon icon={ArrowLeft01Icon} />
              Another file
            </Button>
            <Button
              state={runCheck.state}
              loadingLabel="Checking…"
              successLabel="Checked"
              errorLabel="Not checked"
              onClick={() => {
                setRefusal(null);
                void runCheck.run(step.batch);
              }}
            >
              Check the rows
            </Button>
          </>
        ) : null}
        {step.kind === "review" ? (
          <ReviewActions
            kind={kind}
            check={step.check}
            noun={noun}
            linesAction={linesAction ?? `Add ${noun.many}`}
            busy={busy}
            commitState={runCommit.state}
            onBack={() => {
              back(step.batch);
            }}
            onCommit={(skipInvalid) => {
              setRefusal(null);
              void runCommit.run({ batch: step.batch, skipInvalid });
            }}
            onLines={() => {
              onLines?.(step.check.lines ?? []);
              onClose();
            }}
          />
        ) : null}
        {step.kind === "done" ? (
          <DialogClose render={<Button type="button" />}>Done</DialogClose>
        ) : null}
      </DialogFooter>
    </div>
  );
}

const STEP_LABELS = [
  ["upload", "Upload"],
  ["match", "Match columns"],
  ["review", "Review"],
] as const;

/** Where the person is: three steps, the current one marked for screen readers too. */
function StepTrail({ step }: { step: Step["kind"] }): React.JSX.Element | null {
  if (step === "done") return null;
  const at = STEP_LABELS.findIndex(([key]) => key === step);
  return (
    <ol aria-label="Import steps" className="flex flex-wrap gap-x-3 gap-y-1 pt-1 text-xs">
      {STEP_LABELS.map(([key, label], index) => (
        <li
          key={key}
          aria-current={index === at ? "step" : undefined}
          className={cn(
            "flex items-center gap-1.5",
            index === at ? "font-medium text-foreground" : "text-muted-foreground",
          )}
        >
          <span
            aria-hidden="true"
            className={cn(
              "flex size-5 items-center justify-center rounded-full text-2xs tabular-nums",
              index <= at ? "bg-primary text-primary-foreground" : "bg-muted",
            )}
          >
            {index + 1}
          </span>
          {label}
        </li>
      ))}
    </ol>
  );
}

// ── step 1 · upload ─────────────────────────────────────────────────────────

function UploadStep({
  file,
  onFile,
}: {
  file: File | null;
  onFile: (file: File | null) => void;
}): React.JSX.Element {
  const inputRef = useRef<HTMLInputElement>(null);
  const tooBig = file !== null && file.size > MAX_BYTES;

  return (
    <div className="flex flex-col gap-3">
      <input
        ref={inputRef}
        type="file"
        data-testid="import-file-input"
        accept={ACCEPT}
        className="sr-only"
        tabIndex={-1}
        aria-hidden="true"
        onChange={(event) => {
          const picked = event.target.files?.[0] ?? null;
          onFile(picked);
          event.target.value = "";
        }}
      />
      <div className="flex flex-col items-start gap-3 rounded-xl border border-dashed border-border p-4 sm:flex-row sm:items-center">
        <span
          aria-hidden="true"
          className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground"
        >
          <Icon icon={FileSpreadsheetIcon} />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          {file === null ? (
            <p className="text-sm text-foreground">No file chosen yet.</p>
          ) : (
            <p className="text-sm font-medium wrap-break-word text-foreground">
              {file.name}{" "}
              <span className="font-normal text-muted-foreground">
                · {formatFileSize(file.size)}
              </span>
            </p>
          )}
          <p id="import-file-hint" className="text-xs text-muted-foreground">
            An Excel workbook (.xlsx) or a CSV, up to 10 MB and 5,000 rows. Its first row should
            name the columns.
          </p>
        </div>
        <Button
          variant="outline"
          aria-describedby="import-file-hint"
          onClick={() => {
            inputRef.current?.click();
          }}
        >
          <Icon icon={FileImportIcon} />
          {file === null ? "Choose a file" : "Choose another"}
        </Button>
      </div>
      {tooBig ? (
        <p role="alert" className="text-sm text-danger">
          Files up to 10 MB.
        </p>
      ) : null}
    </div>
  );
}

// ── step 2 · match columns ──────────────────────────────────────────────────

/** The column a field is matched to, if any. */
function columnOf(mapping: ImportMapping, key: string): number | null {
  return mapping[key] ?? null;
}

/** The field a column is matched to, if any. */
function fieldOfColumn(mapping: ImportMapping, column: number): string | null {
  return Object.entries(mapping).find(([, value]) => value === column)?.[0] ?? null;
}

/** The first two values of a column the person will recognise. */
function samplesOf(batch: ImportBatch, column: number): string[] {
  return batch.sample
    .map((row) => row[column]?.trim() ?? "")
    .filter((value) => value !== "")
    .slice(0, 2);
}

function MatchStep({
  batch,
  mapping,
  onMapping,
  mapProblems,
  mode,
  onMode,
  busy,
  onReread,
}: {
  batch: ImportBatch;
  mapping: ImportMapping;
  onMapping: (next: ImportMapping) => void;
  mapProblems: Readonly<Record<string, string>>;
  /** Price imports only. */
  mode: ImportMode | null;
  onMode: (mode: ImportMode) => void;
  busy: boolean;
  onReread: (sheet: string | undefined, headerRow: number | undefined) => void;
}): React.JSX.Element {
  const [headerRow, setHeaderRow] = useState(String(batch.headerRow));
  const fieldItems = [
    { value: SKIP, label: "Skip this column" },
    ...batch.fields.map((field) => ({
      value: field.key,
      label: field.required ? `${field.label} (required)` : field.label,
    })),
  ];
  const fieldsByKey = new Map(batch.fields.map((field) => [field.key, field]));
  // A required field with no column, or a problem the backend put on a field with none.
  const unplaced = Object.entries(mapProblems).filter(([key]) => columnOf(mapping, key) === null);
  const missing = batch.fields.filter(
    (field) => field.required && columnOf(mapping, field.key) === null,
  );
  const rowNumber = Number(headerRow);
  const rowValid = Number.isInteger(rowNumber) && rowNumber >= 1 && rowNumber <= 1000;

  const choose = (column: number, value: string): void => {
    const next: Record<string, number> = {};
    for (const [key, at] of Object.entries(mapping)) {
      // A field matches one column, and a column one field.
      if (at !== column && key !== value) next[key] = at;
    }
    if (value !== SKIP) next[value] = column;
    onMapping(next);
  };

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">{batch.fileName}</span>
        {batch.sheet === null ? "" : ` · sheet ${batch.sheet}`} · {formatCount(batch.rowCount)}{" "}
        {batch.rowCount === 1 ? "row" : "rows"} under row {batch.headerRow}
      </p>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        {batch.sheets.length > 1 ? (
          <Field className="sm:w-56">
            <FieldLabel htmlFor="import-sheet">Sheet</FieldLabel>
            <Select
              items={batch.sheets.map((sheet) => ({ value: sheet, label: sheet }))}
              value={batch.sheet}
              disabled={busy}
              onValueChange={(next) => {
                if (typeof next === "string" && next !== batch.sheet) onReread(next, undefined);
              }}
            >
              <SelectTrigger id="import-sheet" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {batch.sheets.map((sheet) => (
                  <SelectItem key={sheet} value={sheet}>
                    {sheet}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        ) : null}
        <Field className="sm:w-40" data-invalid={rowValid ? undefined : true}>
          <FieldLabel htmlFor="import-header-row">Column names on row</FieldLabel>
          <Input
            id="import-header-row"
            inputMode="numeric"
            value={headerRow}
            aria-invalid={rowValid ? undefined : true}
            onChange={(event) => {
              setHeaderRow(event.target.value);
            }}
          />
        </Field>
        <Button
          variant="outline"
          disabled={busy || !rowValid || rowNumber === batch.headerRow}
          onClick={() => {
            onReread(batch.sheet ?? undefined, rowNumber);
          }}
        >
          Read again
        </Button>
      </div>

      <ul
        aria-label="Columns in your file"
        className="flex flex-col divide-y divide-border rounded-lg border border-border"
      >
        {batch.headers.map((header, column) => {
          const chosen = fieldOfColumn(mapping, column);
          const field = chosen === null ? undefined : fieldsByKey.get(chosen);
          const problem = chosen === null ? undefined : mapProblems[chosen];
          const selectId = `import-column-${String(column)}`;
          const samples = samplesOf(batch, column);
          return (
            <li
              key={`${header}-${String(column)}`}
              className="grid gap-2 p-3 md:grid-cols-2 md:items-start md:gap-4"
            >
              <div className="flex min-w-0 flex-col gap-0.5">
                <Label htmlFor={selectId} className="text-sm font-medium wrap-break-word">
                  {header}
                </Label>
                <p className="truncate text-xs text-muted-foreground">
                  {samples.length === 0 ? "Empty in the first rows" : samples.join(" · ")}
                </p>
              </div>
              <Field data-invalid={problem === undefined ? undefined : true}>
                <Select
                  items={fieldItems}
                  value={chosen ?? SKIP}
                  disabled={busy}
                  onValueChange={(next) => {
                    if (typeof next === "string") choose(column, next);
                  }}
                >
                  <SelectTrigger
                    id={selectId}
                    className="w-full"
                    aria-invalid={problem === undefined ? undefined : true}
                    aria-describedby={`${selectId}-help`}
                  >
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {fieldItems.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription id={`${selectId}-help`}>
                  {field === undefined ? "Not imported." : field.help || field.label}
                </FieldDescription>
                <FieldError>{problem}</FieldError>
              </Field>
            </li>
          );
        })}
      </ul>

      {missing.length > 0 || unplaced.length > 0 ? (
        <div role="note" className="rounded-md bg-warning-soft p-3 text-sm text-foreground">
          {missing.length > 0 ? (
            <p>Still to match: {missing.map((field) => field.label).join(", ")}.</p>
          ) : null}
          {unplaced
            .filter(([key]) => !missing.some((field) => field.key === key))
            .map(([key, reason]) => (
              <p key={key}>
                {fieldsByKey.get(key)?.label ?? key}: {reason}.
              </p>
            ))}
        </div>
      ) : null}

      {mode === null ? null : (
        <Field>
          <FieldLabel id="import-mode-label">The rates already in the list</FieldLabel>
          <RadioGroup
            aria-labelledby="import-mode-label"
            value={mode}
            onValueChange={(value) => {
              const chosen = IMPORT_MODES.find((item) => item === value);
              if (chosen !== undefined) onMode(chosen);
            }}
            className="flex flex-col gap-2"
          >
            {IMPORT_MODES.map((item) => (
              <div key={item} className="flex items-start gap-2">
                <RadioGroupItem id={`import-mode-${item}`} value={item} className="mt-0.5" />
                <Label
                  htmlFor={`import-mode-${item}`}
                  className="flex flex-col items-start gap-0.5 font-normal"
                >
                  <span className="font-medium">{MODE_TEXT[item].label}</span>
                  <span className="text-xs text-muted-foreground">{MODE_TEXT[item].help}</span>
                </Label>
              </div>
            ))}
          </RadioGroup>
        </Field>
      )}
    </div>
  );
}

// ── step 3 · review ─────────────────────────────────────────────────────────

/** "territory" → "Territory": a value the backend works out, not a field of the sheet. */
function humanize(key: string): string {
  const words = key.replace(/_/g, " ");
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
}

function labelOf(fields: readonly ImportField[], key: string): string {
  return fields.find((field) => field.key === key)?.label ?? humanize(key);
}

function ReviewStep({
  batch,
  check,
  mapping,
  noun,
}: {
  batch: ImportBatch;
  check: ImportCheck;
  mapping: ImportMapping;
  noun: ImportNoun;
}): React.JSX.Element {
  const problems = check.errorRows.flatMap((row) =>
    Object.entries(row.errors).map(([field, reason]) => ({ row: row.row, field, reason })),
  );
  // The preview's columns: the matched fields, in the file's column order, then what the
  // backend worked out from them (the product a code names, a partner's territory), less ids.
  const matched = Object.entries(mapping)
    .sort(([, a], [, b]) => a - b)
    .map(([key]) => key)
    .filter((key) => check.preview.some((row) => key in row.values));
  const fieldKeys = new Set(batch.fields.map((field) => field.key));
  const derived = [...new Set(check.preview.flatMap((row) => Object.keys(row.values)))].filter(
    (key) => !fieldKeys.has(key) && !/_(id|row)$/.test(key),
  );
  const columns = [...matched, ...derived];
  const warnings = Object.entries(check.columnWarnings);
  const headCell = "px-3 py-2 text-left text-xs font-medium text-muted-foreground";
  const cell = "px-3 py-2 align-top text-sm";

  return (
    <div className="flex flex-col gap-4">
      <div aria-live="polite" className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-foreground">
          {formatCount(check.total)} {check.total === 1 ? "row" : "rows"}:
        </p>
        <Badge variant="success" dot>
          {formatCount(check.ok)} ready
        </Badge>
        {check.errors > 0 ? (
          <Badge variant="danger" dot>
            {formatCount(check.errors)} with errors
          </Badge>
        ) : null}
      </div>

      {warnings.length > 0 ? (
        <ul
          aria-label="About whole columns"
          className="flex flex-col gap-1 rounded-md bg-warning-soft p-3 text-sm text-foreground"
        >
          {warnings.map(([key, message]) => (
            <li key={key}>
              <span className="font-medium">{labelOf(batch.fields, key)}:</span> {message}
            </li>
          ))}
        </ul>
      ) : null}

      {problems.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h3 id="import-errors-title" className="text-sm font-semibold text-foreground">
            Rows with errors
          </h3>
          <div
            role="region"
            aria-labelledby="import-errors-title"
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be reachable by keyboard (WCAG 2.1.1)
            tabIndex={0}
            className="max-h-64 overflow-auto rounded-lg border border-border focus-ring-inset"
          >
            <table className="w-full border-collapse">
              <caption className="sr-only">Rows with errors, by their row in your sheet</caption>
              <thead className="sticky top-0 bg-panel">
                <tr>
                  <th scope="col" className={headCell}>
                    Row
                  </th>
                  <th scope="col" className={headCell}>
                    Column
                  </th>
                  <th scope="col" className={headCell}>
                    What&apos;s wrong
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {problems.map((problem) => (
                  <tr key={`${String(problem.row)}-${problem.field}`}>
                    <td className={cn(cell, "tabular-nums")}>{problem.row}</td>
                    <td className={cell}>{labelOf(batch.fields, problem.field)}</td>
                    <td className={cn(cell, "text-danger")}>{problem.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {check.errors > check.errorRows.length ? (
            <p className="text-xs text-muted-foreground">
              The first {formatCount(check.errorRows.length)} rows with errors are shown.
            </p>
          ) : null}
        </section>
      ) : null}

      {check.preview.length > 0 ? (
        <section className="flex flex-col gap-2">
          <h3 id="import-preview-title" className="text-sm font-semibold text-foreground">
            {check.ok > check.preview.length
              ? `The first ${formatCount(check.preview.length)} ${noun.many}, as they will be saved`
              : `The ${noun.many}, as they will be saved`}
          </h3>
          <div
            role="region"
            aria-labelledby="import-preview-title"
            // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be reachable by keyboard (WCAG 2.1.1)
            tabIndex={0}
            className="max-h-72 overflow-auto rounded-lg border border-border focus-ring-inset"
          >
            <table className="w-full min-w-max border-collapse">
              <caption className="sr-only">Ready rows, as they will be saved</caption>
              <thead className="sticky top-0 bg-panel">
                <tr>
                  <th scope="col" className={headCell}>
                    Row
                  </th>
                  {columns.map((key) => (
                    <th key={key} scope="col" className={headCell}>
                      {labelOf(batch.fields, key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {check.preview.map((row) => (
                  <tr key={row.row}>
                    <td className={cn(cell, "text-muted-foreground tabular-nums")}>{row.row}</td>
                    {columns.map((key) => (
                      <td key={key} className={cell}>
                        {row.values[key] ?? ""}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <p className="text-sm text-muted-foreground">
          No row is ready yet. Fix the file, or go back and match the columns again.
        </p>
      )}
    </div>
  );
}

function ReviewActions({
  kind,
  check,
  noun,
  linesAction,
  busy,
  commitState,
  onBack,
  onCommit,
  onLines,
}: {
  kind: ImportKind;
  check: ImportCheck;
  noun: ImportNoun;
  linesAction: string;
  busy: boolean;
  commitState: AsyncActionState;
  onBack: () => void;
  onCommit: (skipInvalid: boolean) => void;
  onLines: () => void;
}): React.JSX.Element {
  // Which commit button was pressed: only that one shows its progress.
  const [pressed, setPressed] = useState<"all" | "good" | null>(null);
  const goodOnlyLocked = busy && pressed !== "good";
  const allLocked = check.errors > 0 || check.ok === 0 || (busy && pressed !== "all");
  return (
    <>
      <Button variant="outline" disabled={busy} onClick={onBack}>
        <Icon icon={ArrowLeft01Icon} />
        Back to matching
      </Button>
      {kind === "lines" ? (
        <Button disabled={check.ok === 0} onClick={onLines}>
          {check.errors > 0
            ? `${linesAction}: the ${formatCount(check.ok)} good ${check.ok === 1 ? noun.one : noun.many}`
            : linesAction}
        </Button>
      ) : (
        <>
          {check.errors > 0 && check.ok > 0 ? (
            <Button
              variant="outline"
              disabled={goodOnlyLocked}
              state={pressed === "good" ? commitState : "idle"}
              loadingLabel="Importing…"
              successLabel="Imported"
              errorLabel="Not imported"
              onClick={() => {
                setPressed("good");
                onCommit(true);
              }}
            >
              Import good rows only
            </Button>
          ) : null}
          <Button
            disabled={allLocked}
            state={pressed === "all" ? commitState : "idle"}
            loadingLabel="Importing…"
            successLabel="Imported"
            errorLabel="Not imported"
            onClick={() => {
              setPressed("all");
              onCommit(false);
            }}
          >
            Import {formatCount(check.ok)} {check.ok === 1 ? noun.one : noun.many}
          </Button>
        </>
      )}
    </>
  );
}

function DoneStep({
  result,
  noun,
}: {
  result: ImportCommitResult;
  noun: ImportNoun;
}): React.JSX.Element {
  return (
    <div role="status" className="flex flex-col items-center gap-2 py-6 text-center">
      <span className="flex size-10 items-center justify-center rounded-full bg-success-soft text-success">
        <Icon icon={CheckmarkCircle02Icon} />
      </span>
      <p className="text-base font-semibold text-foreground">
        {formatCount(result.created)} {result.created === 1 ? noun.one : noun.many}{" "}
        {noun.one === "partner" ? "created" : "written"}
        {result.skipped > 0 ? `, ${formatCount(result.skipped)} skipped` : ""}.
      </p>
    </div>
  );
}

function RefusalNote({ refusal }: { refusal: ImportRefusal | null }): React.JSX.Element | null {
  if (refusal === null || (refusal.message === null && refusal.rows.length === 0)) return null;
  return (
    <div role="alert" className="mt-4 flex flex-col gap-1 rounded-md bg-danger-soft p-3 text-sm">
      {refusal.message === null ? null : <p className="text-danger">{refusal.message}</p>}
      {refusal.rows.length > 0 ? (
        <ul className="flex flex-col gap-0.5 text-foreground">
          {refusal.rows.slice(0, 10).map((row) => (
            <li key={`${String(row.row)}-${row.field}`}>
              Row {row.row}, {row.field}: {row.reason}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
