"use client";

import { Add01Icon, Database01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import type { LookupItem, LookupList } from "@/features/lookups/api/lookups.schemas";
import { useAddLookupItem, useUpdateLookupItem } from "@/features/masters/api/masters.mutations";
import {
  listTakesKind,
  listTakesQuality,
  listTakesSortOrder,
  LOOKUP_CODE_MAX_LENGTH,
  LOOKUP_CODE_PATTERN,
  LOOKUP_NAME_MAX_LENGTH,
  LOOKUP_SORT_ORDER_LIMIT,
  type LookupCreateRequest,
  type LookupUpdateRequest,
} from "@/features/masters/api/masters.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/masters/components/lookup-list-panel.tsx",
  dataId: "MSTR-009",
});

interface ListCopy {
  /** The tab and card title: "Lead sources". */
  readonly title: string;
  /** One row: "lead source". */
  readonly one: string;
  /** Where the list is used, for whoever edits it. */
  readonly description: string;
}

export const LIST_COPY: Readonly<Record<LookupList, ListCopy>> = {
  "lead-sources": {
    title: "Lead sources",
    one: "lead source",
    description:
      "Where a lead came from. Picked on every new lead; its quality counts in the score.",
  },
  "mis-systems": {
    title: "Irrigation systems",
    one: "irrigation system",
    description: "The system a lead is asking about: drip, sprinkler and so on.",
  },
  "lost-reasons": {
    title: "Lost reasons",
    one: "lost reason",
    description: "Asked for whenever a lead is marked lost.",
  },
  crops: {
    title: "Crops",
    one: "crop",
    description: "The crops on a lead's land.",
  },
  "meeting-types": {
    title: "Meeting types",
    one: "meeting type",
    description: "What a task's meeting is for, in the day planner.",
  },
  "complaint-types": {
    title: "Complaint types",
    one: "complaint type",
    description: "What a complaint is about; complaint targets can be set by type.",
  },
};

/** "Agri fair" → "agri_fair": a starting point for the code, which stays editable. */
export function codeFromName(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, LOOKUP_CODE_MAX_LENGTH);
}

/**
 * MSTR-009 · One admin list: every row, switched-off ones too, and — for those who may edit
 * masters — adding a row and switching one on or off. Rows are never renamed or deleted: a
 * lead keeps the reason it was lost with, so a row that is no longer wanted is switched off.
 */
export function LookupListPanel({
  list,
  canEdit,
}: {
  list: LookupList;
  canEdit: boolean;
}): React.JSX.Element {
  const query = useQuery(lookupListQueryOptions(list));
  const copy = LIST_COPY[list];
  const [adding, setAdding] = useState(false);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle>{copy.title}</CardTitle>
          <CardDescription>{copy.description}</CardDescription>
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
            Add a {copy.one}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        <QueryView
          query={query}
          pending={<ListSkeleton />}
          isEmpty={(rows) => rows.length === 0}
          empty={
            <EmptyState
              icon={Database01Icon}
              title={`No ${copy.title.toLowerCase()} yet`}
              description={
                canEdit ? `Add the first ${copy.one}.` : "Ask an administrator to add one."
              }
              className="py-8"
            />
          }
        >
          {(rows) => <ListTable list={list} rows={rows} canEdit={canEdit} />}
        </QueryView>
      </CardContent>
      {canEdit ? (
        <AddItemDialog
          list={list}
          open={adding}
          onOpenChange={setAdding}
          existing={query.data ?? []}
        />
      ) : null}
    </Card>
  );
}

function ListTable({
  list,
  rows,
  canEdit,
}: {
  list: LookupList;
  rows: readonly LookupItem[];
  canEdit: boolean;
}): React.JSX.Element {
  const active = rows.filter((row) => row.isActive).length;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">
        {formatNumber(active)} in use
        {rows.length > active ? `, ${formatNumber(rows.length - active)} switched off` : ""}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">{LIST_COPY[list].title}</caption>
          <thead>
            <tr className="border-b border-border text-xs text-muted-foreground">
              <th scope="col" className="py-2 pr-3 text-left font-medium">
                Name
              </th>
              <th scope="col" className="py-2 pr-3 text-left font-medium">
                Code
              </th>
              {listTakesSortOrder(list) ? (
                <th scope="col" className="py-2 pr-3 text-right font-medium">
                  Order
                </th>
              ) : null}
              {listTakesQuality(list) && canEdit ? (
                <th scope="col" className="py-2 pr-3 text-right font-medium">
                  Quality
                </th>
              ) : null}
              {listTakesKind(list) ? (
                <th scope="col" className="py-2 pr-3 text-left font-medium">
                  Kind
                </th>
              ) : null}
              <th scope="col" className="py-2 pr-3 text-left font-medium">
                Status
              </th>
              {canEdit ? (
                <th scope="col" className="py-2 text-right font-medium">
                  <span className="sr-only">Actions</span>
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <ListRow key={row.id} list={list} row={row} canEdit={canEdit} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ListRow({
  list,
  row,
  canEdit,
}: {
  list: LookupList;
  row: LookupItem;
  canEdit: boolean;
}): React.JSX.Element {
  const update = useUpdateLookupItem(list);
  const [editing, setEditing] = useState(false);
  const editable = listTakesSortOrder(list) || listTakesQuality(list);
  const toggle = useAsyncAction({
    action: () => update.mutateAsync({ itemId: row.id, body: { is_active: !row.isActive } }),
    logger: log,
    fn: "handleToggleLookupItem",
    dataId: "MSTR-009",
    onSuccess: (item) => {
      toast.success(item.isActive ? `${item.name} switched on` : `${item.name} switched off`, {
        description: item.isActive
          ? "It can be picked again."
          : "Records that use it keep it; new ones can't pick it.",
      });
    },
    onError: (error) => {
      toast.error(`${row.name} not changed`, { description: toUserFacingError(error).description });
    },
  });

  return (
    <tr className="border-b border-border last:border-0">
      <th
        scope="row"
        className={
          row.isActive
            ? "py-2 pr-3 text-left font-normal text-foreground"
            : "py-2 pr-3 text-left font-normal text-muted-foreground"
        }
      >
        {row.name}
      </th>
      <td className="py-2 pr-3 font-mono text-xs text-muted-foreground">{row.code}</td>
      {listTakesSortOrder(list) ? (
        <td className="py-2 pr-3 text-right text-foreground tabular-nums">
          {row.sortOrder === null ? "—" : formatNumber(row.sortOrder)}
        </td>
      ) : null}
      {listTakesQuality(list) && canEdit ? (
        <td className="py-2 pr-3 text-right text-foreground tabular-nums">{row.quality ?? "—"}</td>
      ) : null}
      {listTakesKind(list) ? (
        <td className="py-2 pr-3 text-foreground">
          {row.kind === null ? "—" : row.kind === "won" ? "Won" : "Lost"}
        </td>
      ) : null}
      <td className="py-2 pr-3">
        {row.isActive ? (
          <Badge size="sm" variant="success">
            In use
          </Badge>
        ) : (
          <Badge size="sm" variant="neutral">
            Switched off
          </Badge>
        )}
      </td>
      {canEdit ? (
        <td className="py-1 text-right whitespace-nowrap">
          {editable ? (
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Edit ${row.name}`}
              onClick={() => {
                setEditing(true);
              }}
            >
              Edit
            </Button>
          ) : null}
          <EditItemDialog list={list} row={row} open={editing} onOpenChange={setEditing} />
          <Button
            variant="ghost"
            size="sm"
            aria-label={row.isActive ? `Switch off ${row.name}` : `Switch on ${row.name}`}
            state={toggle.state}
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
            onClick={() => {
              void toggle.run();
            }}
          >
            {row.isActive ? "Switch off" : "Switch on"}
          </Button>
        </td>
      ) : null}
    </tr>
  );
}

interface Draft {
  readonly name: string;
  readonly code: string;
  /** The code was typed, so it no longer follows the name. */
  readonly codeTouched: boolean;
  readonly sortOrder: string;
  readonly quality: string;
  readonly kind: "lost" | "won";
}

const EMPTY_DRAFT: Draft = {
  name: "",
  code: "",
  codeTouched: false,
  sortOrder: "",
  quality: "",
  kind: "lost",
};

type DraftField = "name" | "code" | "sortOrder" | "quality";

/** What is wrong with a new row before it is sent, in the form's words. */
export function draftProblems(
  list: LookupList,
  draft: Draft,
  existing: readonly LookupItem[],
): Partial<Record<DraftField, string>> {
  const problems: Partial<Record<DraftField, string>> = {};
  const name = draft.name.trim();
  const code = draft.code.trim();
  if (name === "") problems.name = "Enter the name.";
  if (code === "") {
    problems.code = "Enter the code.";
  } else if (!LOOKUP_CODE_PATTERN.test(code)) {
    problems.code = "Lowercase letters, digits and underscores only, like agri_fair.";
  } else if (existing.some((item) => item.code === code)) {
    problems.code = "Already in use.";
  }
  if (listTakesSortOrder(list)) {
    const sortProblem = sortOrderProblem(draft.sortOrder);
    if (sortProblem !== null) problems.sortOrder = sortProblem;
  }
  if (listTakesQuality(list)) {
    const qualityProblem = qualityProblemOf(draft.quality);
    if (qualityProblem !== null) problems.quality = qualityProblem;
  }
  return problems;
}

/** An empty box is fine; otherwise a whole number within the backend's bound (BE-026). */
function sortOrderProblem(text: string): string | null {
  const value = text.trim();
  if (value === "") return null;
  if (!/^-?\d+$/.test(value)) return "A whole number, like 10.";
  if (Math.abs(Number(value)) > LOOKUP_SORT_ORDER_LIMIT) {
    return "At most 1,000,000 either way.";
  }
  return null;
}

function qualityProblemOf(text: string): string | null {
  const value = text.trim();
  if (value === "") return null;
  const quality = Number(value);
  return !/^\d+(\.\d+)?$/.test(value) || quality < 0 || quality > 1
    ? "A number from 0 to 1, like 0.6."
    : null;
}

/** BE-026 · What an edit sends: only a sort order or quality that changed. */
export function updateRequestOf(
  list: LookupList,
  row: LookupItem,
  draft: { readonly sortOrder: string; readonly quality: string },
): LookupUpdateRequest {
  const sortOrder = draft.sortOrder.trim();
  const quality = draft.quality.trim();
  return {
    ...(listTakesSortOrder(list) && sortOrder !== "" && Number(sortOrder) !== row.sortOrder
      ? { sort_order: Number(sortOrder) }
      : {}),
    ...(listTakesQuality(list) && quality !== "" && Number(quality) !== Number(row.quality)
      ? { quality }
      : {}),
  };
}

/** The request for a new row: only the fields this list takes, and only those filled in. */
export function createRequestOf(list: LookupList, draft: Draft): LookupCreateRequest {
  const sortOrder = draft.sortOrder.trim();
  const quality = draft.quality.trim();
  return {
    code: draft.code.trim(),
    name: draft.name.trim(),
    ...(listTakesSortOrder(list) && sortOrder !== "" ? { sort_order: Number(sortOrder) } : {}),
    ...(listTakesQuality(list) && quality !== "" ? { quality } : {}),
    ...(listTakesKind(list) ? { kind: draft.kind } : {}),
  };
}

const WIRE_FIELDS: Readonly<Record<string, DraftField>> = {
  name: "name",
  code: "code",
  sort_order: "sortOrder",
  quality: "quality",
};

function AddItemDialog({
  list,
  open,
  onOpenChange,
  existing,
}: {
  list: LookupList;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  existing: readonly LookupItem[];
}): React.JSX.Element {
  const copy = LIST_COPY[list];
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [problems, setProblems] = useState<Partial<Record<DraftField, string>>>({});
  const add = useAddLookupItem(list);

  const close = (): void => {
    onOpenChange(false);
    setDraft(EMPTY_DRAFT);
    setProblems({});
  };

  const submit = useAsyncAction({
    action: () => add.mutateAsync(createRequestOf(list, draft)),
    logger: log,
    fn: "handleAddLookupItem",
    dataId: "MSTR-009",
    onSuccess: (item) => {
      toast.success(`${item.name} added`, { description: copy.title });
      close();
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      const mapped: Partial<Record<DraftField, string>> = {};
      for (const [wire, message] of Object.entries(fields)) {
        const field = WIRE_FIELDS[wire];
        if (field !== undefined) mapped[field] = message;
      }
      if (Object.keys(mapped).length > 0) {
        setProblems(mapped);
        return;
      }
      toast.error(`${copy.title}: not added`, {
        description: toUserFacingError(error).description,
      });
    },
  });

  const set = (patch: Partial<Draft>): void => {
    setDraft((before) => ({ ...before, ...patch }));
  };
  const invalid = (field: DraftField): true | undefined =>
    problems[field] === undefined ? undefined : true;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) onOpenChange(true);
        else close();
      }}
    >
      <DialogContent size="sm">
        <form
          noValidate
          aria-label={`Add a ${copy.one}`}
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            event.preventDefault();
            const found = draftProblems(list, draft, existing);
            setProblems(found);
            if (Object.keys(found).length === 0) void submit.run();
          }}
        >
          <DialogHeader>
            <DialogTitle>Add a {copy.one}</DialogTitle>
            <DialogDescription>
              The name and code can&apos;t change once added. A row no longer wanted is switched
              off, not deleted, so records that use it keep it.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="flex flex-col gap-4">
            <Field data-invalid={invalid("name")}>
              <FieldLabel htmlFor="lookup-name">Name</FieldLabel>
              <Input
                id="lookup-name"
                value={draft.name}
                maxLength={LOOKUP_NAME_MAX_LENGTH}
                autoComplete="off"
                aria-invalid={invalid("name")}
                aria-describedby={invalid("name") ? "lookup-name-error" : undefined}
                onChange={(event) => {
                  const name = event.target.value;
                  set(draft.codeTouched ? { name } : { name, code: codeFromName(name) });
                }}
              />
              <FieldError id="lookup-name-error">{problems.name}</FieldError>
            </Field>
            <Field data-invalid={invalid("code")}>
              <FieldLabel htmlFor="lookup-code">Code</FieldLabel>
              <Input
                id="lookup-code"
                value={draft.code}
                maxLength={LOOKUP_CODE_MAX_LENGTH}
                autoComplete="off"
                spellCheck={false}
                className="font-mono"
                aria-invalid={invalid("code")}
                aria-describedby={invalid("code") ? "lookup-code-error" : "lookup-code-hint"}
                onChange={(event) => {
                  set({ code: event.target.value, codeTouched: true });
                }}
              />
              {problems.code === undefined ? (
                <FieldDescription id="lookup-code-hint">
                  Used in exports and the API. Lowercase with underscores.
                </FieldDescription>
              ) : null}
              <FieldError id="lookup-code-error">{problems.code}</FieldError>
            </Field>
            {listTakesSortOrder(list) ? (
              <Field data-invalid={invalid("sortOrder")}>
                <FieldLabel htmlFor="lookup-sort">Sort order (optional)</FieldLabel>
                <Input
                  id="lookup-sort"
                  inputMode="numeric"
                  value={draft.sortOrder}
                  aria-invalid={invalid("sortOrder")}
                  aria-describedby={invalid("sortOrder") ? "lookup-sort-error" : "lookup-sort-hint"}
                  onChange={(event) => {
                    set({ sortOrder: event.target.value });
                  }}
                />
                {problems.sortOrder === undefined ? (
                  <FieldDescription id="lookup-sort-hint">
                    Lower comes first in pickers.
                  </FieldDescription>
                ) : null}
                <FieldError id="lookup-sort-error">{problems.sortOrder}</FieldError>
              </Field>
            ) : null}
            {listTakesQuality(list) ? (
              <Field data-invalid={invalid("quality")}>
                <FieldLabel htmlFor="lookup-quality">Quality (optional)</FieldLabel>
                <Input
                  id="lookup-quality"
                  inputMode="decimal"
                  value={draft.quality}
                  aria-invalid={invalid("quality")}
                  aria-describedby={
                    invalid("quality") ? "lookup-quality-error" : "lookup-quality-hint"
                  }
                  onChange={(event) => {
                    set({ quality: event.target.value });
                  }}
                />
                {problems.quality === undefined ? (
                  <FieldDescription id="lookup-quality-hint">
                    0 to 1: how likely a lead from this source is to buy. It counts in the score.
                  </FieldDescription>
                ) : null}
                <FieldError id="lookup-quality-error">{problems.quality}</FieldError>
              </Field>
            ) : null}
            {listTakesKind(list) ? (
              <Field>
                <FieldLabel id="lookup-kind-label">Kind</FieldLabel>
                <ToggleGroup
                  aria-labelledby="lookup-kind-label"
                  aria-describedby="lookup-kind-hint"
                  value={[draft.kind]}
                  onValueChange={(next) => {
                    const chosen = next[0];
                    if (chosen === "lost" || chosen === "won") set({ kind: chosen });
                  }}
                >
                  <ToggleGroupItem value="lost">Lost</ToggleGroupItem>
                  <ToggleGroupItem value="won">Won</ToggleGroupItem>
                </ToggleGroup>
                <FieldDescription id="lookup-kind-hint">
                  Whether it explains a lost lead or a won one.
                </FieldDescription>
              </Field>
            ) : null}
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
              errorLabel="Not added"
            >
              Add
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** BE-026 · A row's place in pickers and, for a source, its quality. Name and code never change. */
function EditItemDialog({
  list,
  row,
  open,
  onOpenChange,
}: {
  list: LookupList;
  row: LookupItem;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): React.JSX.Element {
  const initial = {
    sortOrder: row.sortOrder === null ? "" : String(row.sortOrder),
    quality: row.quality ?? "",
  };
  const [draft, setDraft] = useState(initial);
  const [problems, setProblems] = useState<Partial<Record<"sortOrder" | "quality", string>>>({});
  const update = useUpdateLookupItem(list);
  const body = updateRequestOf(list, row, draft);
  const unchanged = Object.keys(body).length === 0;

  const close = (): void => {
    onOpenChange(false);
    setDraft(initial);
    setProblems({});
  };

  const submit = useAsyncAction({
    action: () => update.mutateAsync({ itemId: row.id, body }),
    logger: log,
    fn: "handleEditLookupItem",
    dataId: "MSTR-009",
    onSuccess: (item) => {
      toast.success(`${item.name} saved`, { description: LIST_COPY[list].title });
      close();
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      const mapped: Partial<Record<"sortOrder" | "quality", string>> = {};
      if (fields.sort_order !== undefined) mapped.sortOrder = fields.sort_order;
      if (fields.quality !== undefined) mapped.quality = fields.quality;
      if (Object.keys(mapped).length > 0) {
        setProblems(mapped);
        return;
      }
      toast.error(`${row.name} not saved`, { description: toUserFacingError(error).description });
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) onOpenChange(true);
        else close();
      }}
    >
      <DialogContent size="sm">
        <form
          noValidate
          aria-label={`Edit ${row.name}`}
          className="flex min-h-0 flex-1 flex-col text-left"
          onSubmit={(event) => {
            event.preventDefault();
            const found: Partial<Record<"sortOrder" | "quality", string>> = {};
            const sortProblem = listTakesSortOrder(list) ? sortOrderProblem(draft.sortOrder) : null;
            const qualityProblem = listTakesQuality(list) ? qualityProblemOf(draft.quality) : null;
            if (sortProblem !== null) found.sortOrder = sortProblem;
            if (qualityProblem !== null) found.quality = qualityProblem;
            setProblems(found);
            if (Object.keys(found).length === 0 && !unchanged) void submit.run();
          }}
        >
          <DialogHeader>
            <DialogTitle>Edit {row.name}</DialogTitle>
            <DialogDescription>
              The name and code stay as they are; records that use this row keep it.
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="flex flex-col gap-4">
            {listTakesSortOrder(list) ? (
              <Field data-invalid={problems.sortOrder === undefined ? undefined : true}>
                <FieldLabel htmlFor={`lookup-edit-sort-${row.id}`}>Sort order</FieldLabel>
                <Input
                  id={`lookup-edit-sort-${row.id}`}
                  inputMode="numeric"
                  value={draft.sortOrder}
                  aria-invalid={problems.sortOrder === undefined ? undefined : true}
                  aria-describedby={`lookup-edit-sort-${row.id}-${problems.sortOrder === undefined ? "hint" : "error"}`}
                  onChange={(event) => {
                    setDraft((before) => ({ ...before, sortOrder: event.target.value }));
                  }}
                />
                {problems.sortOrder === undefined ? (
                  <FieldDescription id={`lookup-edit-sort-${row.id}-hint`}>
                    Lower comes first in pickers.
                  </FieldDescription>
                ) : null}
                <FieldError id={`lookup-edit-sort-${row.id}-error`}>
                  {problems.sortOrder}
                </FieldError>
              </Field>
            ) : null}
            {listTakesQuality(list) ? (
              <Field data-invalid={problems.quality === undefined ? undefined : true}>
                <FieldLabel htmlFor={`lookup-edit-quality-${row.id}`}>Quality</FieldLabel>
                <Input
                  id={`lookup-edit-quality-${row.id}`}
                  inputMode="decimal"
                  value={draft.quality}
                  aria-invalid={problems.quality === undefined ? undefined : true}
                  aria-describedby={`lookup-edit-quality-${row.id}-${problems.quality === undefined ? "hint" : "error"}`}
                  onChange={(event) => {
                    setDraft((before) => ({ ...before, quality: event.target.value }));
                  }}
                />
                {problems.quality === undefined ? (
                  <FieldDescription id={`lookup-edit-quality-${row.id}-hint`}>
                    0 to 1: how likely a lead from this source is to buy. It counts in the score.
                  </FieldDescription>
                ) : null}
                <FieldError id={`lookup-edit-quality-${row.id}-error`}>
                  {problems.quality}
                </FieldError>
              </Field>
            ) : null}
          </DialogBody>
          <DialogFooter>
            <DialogClose
              render={<Button type="button" variant="outline" disabled={submit.isBusy} />}
            >
              Cancel
            </DialogClose>
            <Button
              type="submit"
              disabled={unchanged}
              state={submit.state}
              loadingLabel="Saving…"
              successLabel="Saved"
              errorLabel="Not saved"
            >
              Save
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ListSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the list" className="flex flex-col gap-2">
      {[0, 1, 2, 3, 4].map((row) => (
        <Skeleton key={row} className="h-8 w-full" />
      ))}
    </div>
  );
}
