"use client";

import { Add01Icon, Shield01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
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
import { productCategoriesQueryOptions } from "@/features/products/api/products.queries";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useSetWarrantyTerm } from "@/features/warranty/api/warranty.mutations";
import { warrantyTermsQueryOptions } from "@/features/warranty/api/warranty.queries";
import {
  MAX_WARRANTY_MONTHS,
  type SetWarrantyTermRequest,
  type WarrantyTerm,
} from "@/features/warranty/api/warranty.schemas";
import { monthsText } from "@/features/warranty/lib/warranty-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/warranty/components/warranty-terms-panel.tsx",
  dataId: "MSTR-017",
});

/** The Select's value for the default period, which has no category. */
const DEFAULT_CHOICE = "default";

type TermPhase = "in_force" | "upcoming" | "ended";

const PHASE_LABELS: Readonly<Record<TermPhase, string>> = {
  in_force: "In force",
  upcoming: "Upcoming",
  ended: "Ended",
};

const PHASE_BADGE: Readonly<Record<TermPhase, BadgeVariant>> = {
  in_force: "success",
  upcoming: "info",
  ended: "neutral",
};

/** Where a period stands today. `effectiveTo` is the day the next one starts. */
export function termPhase(term: WarrantyTerm, today: string): TermPhase {
  if (term.effectiveFrom > today) return "upcoming";
  if (term.effectiveTo !== null && term.effectiveTo <= today) return "ended";
  return "in_force";
}

/** "From 1 Apr 2026", "1 Apr 2026 to 31 Mar 2027". */
export function termSpan(term: WarrantyTerm): string {
  if (term.effectiveTo === null) return `From ${formatBusinessDay(term.effectiveFrom)}`;
  return `${formatBusinessDay(term.effectiveFrom)} to ${formatBusinessDay(shiftCalendarDay(term.effectiveTo, -1))}`;
}

function categoryName(term: WarrantyTerm): string {
  return term.category?.name ?? "Default";
}

/**
 * MSTR-017 · Warranty periods: how many months goods stay in warranty, by product category, with
 * a default for every other category. A new period starts tomorrow or later and closes the one
 * in force, so a dispatch already sent keeps the period it left with.
 */
export function WarrantyTermsPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const query = useQuery(warrantyTermsQueryOptions());
  const [setting, setSetting] = useState(false);
  const terms = query.data ?? [];
  const today = todayInIndia();
  // BE-024 · every active category, and any a period already names
  const lookup = useQuery({ ...productCategoriesQueryOptions(), enabled: canEdit });
  const categories = [
    ...new Map([
      ...(lookup.data ?? [])
        .filter((category) => category.isActive)
        .map((category) => [category.id, { id: category.id, name: category.name }] as const),
      ...terms.flatMap((term) =>
        term.category === null
          ? []
          : [[term.category.id, { id: term.category.id, name: term.category.name }] as const],
      ),
    ]).values(),
  ];

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div className="flex flex-col gap-0.5">
          <CardTitle>Warranty periods</CardTitle>
          <CardDescription>
            How long goods stay in warranty from the day they leave, by product category.
          </CardDescription>
        </div>
        {canEdit ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setSetting(true);
            }}
          >
            <Icon icon={Add01Icon} />
            Set a period
          </Button>
        ) : null}
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {query.status === "pending" ? (
          <div
            aria-busy="true"
            aria-label="Loading the warranty periods"
            className="flex flex-col gap-2"
          >
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        ) : query.status === "error" ? (
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        ) : terms.length === 0 ? (
          <EmptyState
            icon={Shield01Icon}
            title="No warranty periods yet"
            description={
              canEdit
                ? "Set the default period first; every category without its own uses it."
                : "An administrator of masters sets them."
            }
            className="py-8"
          />
        ) : (
          <ul aria-label="Warranty periods" className="flex flex-col divide-y divide-border">
            {terms.map((term) => {
              const phase = termPhase(term, today);
              return (
                <li
                  key={term.id}
                  className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
                >
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-sm font-medium text-foreground">
                      {categoryName(term)}
                      {term.category === null ? (
                        <span className="font-normal text-muted-foreground">
                          {" "}
                          · every other category
                        </span>
                      ) : null}
                    </span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {termSpan(term)}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-sm font-semibold text-foreground tabular-nums">
                      {monthsText(term.months)}
                    </span>
                    <Badge variant={PHASE_BADGE[phase]} size="sm">
                      {PHASE_LABELS[phase]}
                    </Badge>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
      <Dialog open={setting} onOpenChange={setSetting}>
        <DialogContent size="sm">
          {setting ? (
            <WarrantyTermForm
              categories={categories}
              onDone={() => {
                setSetting(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

type TermField = "category" | "months" | "from";

const WIRE_FIELDS: Readonly<Record<string, TermField>> = {
  product_category_id: "category",
  months: "months",
  effective_from: "from",
};

/** What the form holds, as typed. */
export interface TermDraft {
  readonly category: string;
  readonly months: string;
  readonly from: string;
}

/** What is wrong before the period can be sent. */
export function termProblems(draft: TermDraft, today: string): Partial<Record<TermField, string>> {
  const months = Number(draft.months);
  const monthsOk =
    draft.months.trim() !== "" &&
    Number.isInteger(months) &&
    months >= 0 &&
    months <= MAX_WARRANTY_MONTHS;
  return {
    ...(monthsOk ? {} : { months: `Whole months, 0 to ${String(MAX_WARRANTY_MONTHS)}.` }),
    ...(draft.from === ""
      ? { from: "Choose the day it starts." }
      : draft.from <= today
        ? { from: "Tomorrow or later: a period never changes goods already sent." }
        : {}),
  };
}

export function requestOfTerm(draft: TermDraft): SetWarrantyTermRequest {
  return {
    product_category_id: draft.category === DEFAULT_CHOICE ? null : draft.category,
    months: Number(draft.months),
    effective_from: draft.from,
  };
}

/** MSTR-017 · Set a period from a future day, for the default or one category. */
export function WarrantyTermForm({
  categories,
  onDone,
}: {
  categories: readonly { readonly id: string; readonly name: string }[];
  onDone: () => void;
}): React.JSX.Element {
  const today = todayInIndia();
  const tomorrow = shiftCalendarDay(today, 1);
  const [draft, setDraft] = useState<TermDraft>({
    category: DEFAULT_CHOICE,
    months: "",
    from: tomorrow,
  });
  const [problems, setProblems] = useState<Partial<Record<TermField, string>>>({});
  const mutation = useSetWarrantyTerm();
  const idempotency = useIdempotencyKey();
  const choices = [
    { value: DEFAULT_CHOICE, label: "Default (every other category)" },
    ...categories.map((category) => ({ value: category.id, label: category.name })),
  ];

  const save = useAsyncAction({
    action: () => {
      const body = requestOfTerm(draft);
      return mutation.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleSetWarrantyTerm",
    dataId: "MSTR-017",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Warranty period set", {
        description: `${monthsText(Number(draft.months))} from ${formatBusinessDay(draft.from)}.`,
      });
      onDone();
    },
    onError: (error) => {
      if (isApiError(error) && error.status === 409) {
        setProblems({
          from: "A period already starts that day for this category. Pick another day.",
        });
        return;
      }
      const mapped: Partial<Record<TermField, string>> = {};
      for (const [wire, message] of Object.entries(readFieldErrors(error) ?? {})) {
        const field = WIRE_FIELDS[wire];
        if (field !== undefined) mapped[field] = message;
      }
      if (Object.keys(mapped).length > 0) {
        setProblems(mapped);
        return;
      }
      toast.error("Period not set", { description: toUserFacingError(error).description });
    },
  });

  const set = (next: Partial<TermDraft>): void => {
    setDraft((before) => ({ ...before, ...next }));
  };
  const invalid = (field: TermField): true | undefined =>
    problems[field] === undefined ? undefined : true;

  return (
    <form
      noValidate
      aria-label="Set a warranty period"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        const found = termProblems(draft, today);
        setProblems(found);
        if (Object.keys(found).length === 0) void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Set a warranty period</DialogTitle>
        <DialogDescription>
          It applies to goods that leave from that day. Goods already sent keep their period.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={invalid("category")}>
          <FieldLabel htmlFor="warranty-category">Category</FieldLabel>
          <Select
            items={choices}
            value={draft.category}
            onValueChange={(next) => {
              if (typeof next === "string") set({ category: next });
            }}
          >
            <SelectTrigger
              id="warranty-category"
              className="w-full"
              aria-invalid={invalid("category")}
              aria-describedby={
                invalid("category") ? "warranty-category-error" : "warranty-category-hint"
              }
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {choices.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {problems.category === undefined ? (
            <FieldDescription id="warranty-category-hint">
              Categories with a period of their own are listed. Others use the default.
            </FieldDescription>
          ) : null}
          <FieldError id="warranty-category-error">{problems.category}</FieldError>
        </Field>

        <Field data-invalid={invalid("months")}>
          <FieldLabel htmlFor="warranty-months">Months</FieldLabel>
          <Input
            id="warranty-months"
            type="number"
            inputMode="numeric"
            min={0}
            max={MAX_WARRANTY_MONTHS}
            step={1}
            value={draft.months}
            aria-invalid={invalid("months")}
            aria-describedby={invalid("months") ? "warranty-months-error" : "warranty-months-hint"}
            onChange={(event) => {
              set({ months: event.target.value });
            }}
          />
          {problems.months === undefined ? (
            <FieldDescription id="warranty-months-hint">0 means no warranty.</FieldDescription>
          ) : null}
          <FieldError id="warranty-months-error">{problems.months}</FieldError>
        </Field>

        <Field data-invalid={invalid("from")}>
          <FieldLabel htmlFor="warranty-from">Starts on</FieldLabel>
          <Input
            id="warranty-from"
            type="date"
            min={tomorrow}
            value={draft.from}
            aria-invalid={invalid("from")}
            aria-describedby={invalid("from") ? "warranty-from-error" : "warranty-from-hint"}
            onChange={(event) => {
              set({ from: event.target.value });
            }}
          />
          {problems.from === undefined ? (
            <FieldDescription id="warranty-from-hint">
              Tomorrow or later. The period in force ends the day before.
            </FieldDescription>
          ) : null}
          <FieldError id="warranty-from-error">{problems.from}</FieldError>
        </Field>
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
          Set the period
        </Button>
      </DialogFooter>
    </form>
  );
}
