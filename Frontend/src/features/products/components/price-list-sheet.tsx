"use client";

import { ArrowLeft01Icon, DiscountTag01Icon, FileImportIcon } from "@hugeicons/core-free-icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { notFound } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { QueryView } from "@/components/patterns/query-view";
import { SearchField } from "@/components/patterns/search-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ImportDialog } from "@/features/imports/components/import-dialog";
import { RATE_SHEET_PAGE_SIZE } from "@/features/products/api/products.api";
import {
  useClosePriceList,
  usePublishPriceList,
  useSaveRates,
} from "@/features/products/api/products.mutations";
import {
  priceListItemsQueryOptions,
  priceListQueryOptions,
  productKeys,
} from "@/features/products/api/products.queries";
import type { PriceList, PriceListItem } from "@/features/products/api/products.schemas";
import { Pager } from "@/features/products/components/pager";
import { PHASE_BADGE, PriceListForm } from "@/features/products/components/price-lists-panel";
import {
  dayText,
  PHASE_LABELS,
  phaseOf,
  rateProblem,
  salesTypeOf,
  scopeInSentence,
  scopeOf,
  windowOf,
} from "@/features/products/lib/product-labels";
import { readRefusal } from "@/features/products/lib/refusals";
import { useCan } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { isApiError } from "@/lib/api/errors";
import { formatCount, formatInr, shiftCalendarDay, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/products/components/price-list-sheet.tsx",
  dataId: "MSTR-006",
});

type Opened = "publish" | "close" | "copy" | null;

/**
 * MSTR-006 · One price list: its scope and dates, and its rate per product. A draft's rates are
 * typed in place, kept across pages and searches until saved; publishing puts it into force.
 * A published list is read-only: it can be closed from a date, or a new list started from it.
 */
export function PriceListSheet({ listId }: { listId: string }): React.JSX.Element {
  const query = useQuery(priceListQueryOptions(listId));
  if (query.status === "pending") return <PriceListSheetSkeleton />;
  if (query.status === "error") {
    if (isApiError(query.error) && query.error.status === 404) notFound();
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <SheetView key={query.data.id} list={query.data} />;
}

function SheetView({ list }: { list: PriceList }): React.JSX.Element {
  const canEdit = useCan("pricing", "edit");
  const [q, setQ] = useState("");
  const [unpriced, setUnpriced] = useState(false);
  const [page, setPage] = useState(1);
  const [edits, setEdits] = useState<ReadonlyMap<string, string>>(new Map());
  const [opened, setOpened] = useState<Opened>(null);
  // The import is its own dialog, not one of the shared dialog's forms.
  const [importing, setImporting] = useState(false);
  const items = useQuery(priceListItemsQueryOptions(list.id, q, unpriced, page));
  const save = useSaveRates();
  const idempotency = useIdempotencyKey();
  const phase = phaseOf(list);
  const editable = canEdit && list.status === "draft";
  const queryClient = useQueryClient();
  const refreshList = (): void => {
    void queryClient.invalidateQueries({ queryKey: productKeys.all });
  };
  const problems = [...edits.values()].filter((value) => rateProblem(value) !== null).length;

  const saveRates = useAsyncAction({
    action: () => {
      const body = { listId: list.id, edits: [...edits.entries()] };
      return save.mutateAsync({ listId: list.id, edits, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleSaveRates",
    dataId: "MSTR-006",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(`${formatCount(edits.size)} ${edits.size === 1 ? "rate" : "rates"} saved`, {
        description:
          saved.unpriced === 0
            ? "Every active product has a rate."
            : `${formatCount(saved.unpriced)} active ${saved.unpriced === 1 ? "product has" : "products have"} no rate yet.`,
      });
      setEdits(new Map());
    },
    onError: (error) => {
      const read = readRefusal(error);
      toast.error("Rates not saved", {
        description: read.message ?? Object.values(read.fields).join(" "),
      });
    },
  });

  const setRate = (productId: string, original: string | null, value: string): void => {
    setEdits((current) => {
      const next = new Map(current);
      if (value.trim() === (original ?? "")) next.delete(productId);
      else next.set(productId, value);
      return next;
    });
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="flex min-w-0 flex-col gap-1.5">
          <Link
            href="/products?tab=price-lists"
            transitionTypes={["nav-back"]}
            className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
          >
            <Icon icon={ArrowLeft01Icon} size="sm" />
            All price lists
          </Link>
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="text-xl font-semibold wrap-break-word text-foreground">{list.name}</h2>
            <Badge variant={PHASE_BADGE[phase]} dot>
              {PHASE_LABELS[phase]}
            </Badge>
            {list.provisional ? <Badge variant="warning">Stand-in rates</Badge> : null}
          </div>
          <p className="text-sm text-muted-foreground">
            {scopeOf(list)} · {salesTypeOf(list)} · {windowOf(list.from, list.to)}
            {list.publishedAt === null
              ? ""
              : ` · published ${dayText(list.publishedAt.slice(0, 10))}`}
          </p>
          <p className="text-sm text-foreground tabular-nums">
            {formatCount(list.itemCount)} {list.itemCount === 1 ? "rate" : "rates"}
            {list.unpricedCount > 0
              ? ` · ${formatCount(list.unpricedCount)} active ${list.unpricedCount === 1 ? "product" : "products"} without one`
              : " · every active product priced"}
          </p>
        </div>
        {canEdit ? (
          <div className="flex flex-wrap gap-2">
            {list.status === "draft" ? (
              <>
                {/* MSTR-007 · Typed edits would be lost under an import: save or discard first. */}
                <Button
                  variant="outline"
                  disabled={edits.size > 0}
                  onClick={() => {
                    setImporting(true);
                  }}
                >
                  <Icon icon={FileImportIcon} />
                  Import from Excel
                </Button>
                <Button
                  disabled={edits.size > 0}
                  onClick={() => {
                    setOpened("publish");
                  }}
                >
                  Publish
                </Button>
              </>
            ) : null}
            {list.status === "published" && phase !== "ended" ? (
              <Button
                variant="outline"
                onClick={() => {
                  setOpened("close");
                }}
              >
                Close from a date
              </Button>
            ) : null}
            <Button
              variant="outline"
              onClick={() => {
                setOpened("copy");
              }}
            >
              New list from this one
            </Button>
          </div>
        ) : null}
      </div>
      {list.status === "draft" && canEdit && edits.size > 0 ? (
        <p role="note" className="text-sm text-muted-foreground">
          Save your rates before importing or publishing.
        </p>
      ) : null}
      {editable ? (
        <ImportDialog
          kind="price_list_items"
          targetId={list.id}
          open={importing}
          onOpenChange={setImporting}
          title="Import rates from Excel"
          description={`Rates for ${list.name}, from a sheet with a product (item code or description) and a rate on each row.`}
          noun={{ one: "rate", many: "rates" }}
          onCommitted={(result) => {
            refreshList();
            toast.success(
              `${formatCount(result.created)} ${result.created === 1 ? "rate" : "rates"} imported`,
              {
                description:
                  result.skipped > 0
                    ? `${formatCount(result.skipped)} ${result.skipped === 1 ? "row" : "rows"} skipped.`
                    : "Check the sheet, then publish.",
              },
            );
          }}
        />
      ) : null}
      {list.status === "published" ? (
        <p role="note" className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
          A published list never changes, so quotations made under it can always be explained. To
          correct a rate, start a new list from this one.
        </p>
      ) : null}

      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap md:items-center">
        <SearchField
          label="Search the rate sheet"
          placeholder="Product description or item code"
          value={q}
          onSearch={(next) => {
            setQ(next);
            setPage(1);
          }}
        />
        <div className="flex items-center gap-2 px-1">
          <Checkbox
            id="sheet-unpriced"
            checked={unpriced}
            onCheckedChange={(checked) => {
              setUnpriced(checked);
              setPage(1);
            }}
          />
          <Label htmlFor="sheet-unpriced" className="text-sm">
            Without a rate only
          </Label>
        </div>
        {editable ? (
          <div className="flex items-center gap-3 md:ml-auto">
            <p aria-live="polite" className="text-sm text-muted-foreground">
              {edits.size === 0
                ? "No unsaved changes."
                : `${formatCount(edits.size)} unsaved ${edits.size === 1 ? "change" : "changes"}`}
            </p>
            {edits.size > 0 ? (
              <Button
                variant="ghost"
                size="sm"
                disabled={saveRates.isBusy}
                onClick={() => {
                  setEdits(new Map());
                }}
              >
                Discard
              </Button>
            ) : null}
            <Button
              disabled={edits.size === 0 || problems > 0}
              state={saveRates.state}
              loadingLabel="Saving…"
              successLabel="Saved"
              errorLabel="Not saved"
              onClick={() => {
                void saveRates.run();
              }}
            >
              Save rates
            </Button>
          </div>
        ) : null}
      </div>

      <QueryView
        query={items}
        pending={<RateRowsSkeleton />}
        isEmpty={(data) => data.total === 0}
        empty={
          <EmptyState
            icon={DiscountTag01Icon}
            title={q !== "" || unpriced ? "Nothing matches" : "No products to price"}
            description={
              unpriced
                ? "Every active product has a rate in this list."
                : q !== ""
                  ? "Try another description or item code."
                  : "Add products to the catalogue first."
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <ul
              aria-label="Rates"
              className="flex flex-col divide-y divide-border rounded-xl border border-border bg-card"
            >
              {data.items.map((item) => (
                <RateRow
                  key={item.productId}
                  item={item}
                  editable={editable}
                  draft={edits.get(item.productId)}
                  onChange={(value) => {
                    setRate(item.productId, item.rate, value);
                  }}
                />
              ))}
            </ul>
            <Pager
              page={page}
              limit={RATE_SHEET_PAGE_SIZE}
              total={data.total}
              noun="products"
              isPaging={items.isPlaceholderData}
              onPage={setPage}
            />
          </div>
        )}
      </QueryView>

      <Dialog
        open={opened !== null}
        onOpenChange={(open) => {
          if (!open) setOpened(null);
        }}
      >
        <DialogContent size={opened === "copy" ? "md" : "sm"}>
          {opened === "publish" ? (
            <PublishForm
              list={list}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : opened === "close" ? (
            <CloseForm
              list={list}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : opened === "copy" ? (
            <PriceListForm
              source={list}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function RateRow({
  item,
  editable,
  draft,
  onChange,
}: {
  item: PriceListItem;
  editable: boolean;
  draft: string | undefined;
  onChange: (value: string) => void;
}): React.JSX.Element {
  const value = draft ?? item.rate ?? "";
  const problem = draft === undefined ? null : rateProblem(draft);
  const inputId = `rate-${item.productId}`;
  return (
    <li className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="flex flex-wrap items-center gap-2">
          {editable ? (
            <label
              htmlFor={inputId}
              className="text-sm font-medium wrap-break-word text-foreground"
            >
              {item.description}
            </label>
          ) : (
            <span className="text-sm font-medium wrap-break-word text-foreground">
              {item.description}
            </span>
          )}
          {item.active ? null : (
            <Badge variant="neutral" size="sm">
              Switched off
            </Badge>
          )}
          {draft === undefined ? null : (
            <Badge variant="info" size="sm">
              Changed
            </Badge>
          )}
        </span>
        <span className="text-xs text-muted-foreground">Per {item.uom}</span>
      </div>
      {editable ? (
        <div className="flex flex-col gap-1 sm:w-40">
          <div className="flex items-center gap-1.5">
            <span aria-hidden="true" className="text-sm text-muted-foreground">
              ₹
            </span>
            <Input
              id={inputId}
              inputMode="decimal"
              autoComplete="off"
              placeholder="No rate"
              className="text-right tabular-nums"
              value={value}
              aria-invalid={problem === null ? undefined : true}
              aria-describedby={problem === null ? undefined : `${inputId}-error`}
              onChange={(event) => {
                onChange(event.target.value);
              }}
            />
          </div>
          {problem === null ? null : (
            <p id={`${inputId}-error`} className="text-xs text-danger">
              {problem}
            </p>
          )}
        </div>
      ) : (
        <span
          className={
            item.rate === null
              ? "text-sm text-muted-foreground"
              : "text-sm font-medium text-foreground tabular-nums"
          }
        >
          {item.rate === null ? "No rate" : formatInr(item.rate, { paise: true })}
        </span>
      )}
    </li>
  );
}

function PublishForm({
  list,
  onClose,
}: {
  list: PriceList;
  onClose: () => void;
}): React.JSX.Element {
  const publish = usePublishPriceList();
  const idempotency = useIdempotencyKey();
  const [allowUnpriced, setAllowUnpriced] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const missing = list.unpricedCount > 0;
  // Unpriced products are published only once that is ticked.
  const blocked = missing && !allowUnpriced;

  const submit = useAsyncAction({
    action: () => {
      const request = { listId: list.id, allowUnpriced };
      return publish.mutateAsync({ ...request, idempotencyKey: idempotency.keyFor(request) });
    },
    logger: log,
    fn: "handlePublishPriceList",
    dataId: "MSTR-006",
    onSuccess: (result) => {
      idempotency.reset();
      toast.success(`${list.name} published`, {
        description:
          result.closedPredecessorId === null
            ? `Quotations price from it from ${dayText(list.from)}.`
            : "The list it replaces ends the day before it starts.",
      });
      onClose();
    },
    onError: (error) => {
      setRefusal(readRefusal(error).message);
    },
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>Publish {list.name}?</DialogTitle>
        <DialogDescription>
          From {dayText(list.from)}, quotations and orders {scopeInSentence(list)} price from it.
          Once published its rates never change.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        {missing ? (
          <div className="flex items-start gap-2 rounded-md bg-warning-soft p-3">
            <Checkbox
              id="publish-unpriced"
              checked={allowUnpriced}
              onCheckedChange={(checked) => {
                setAllowUnpriced(checked);
              }}
            />
            <Label htmlFor="publish-unpriced" className="text-sm/snug text-foreground">
              Publish without rates for {formatCount(list.unpricedCount)} active{" "}
              {list.unpricedCount === 1 ? "product" : "products"}: they can&apos;t be quoted under
              this list.
            </Label>
          </div>
        ) : null}
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
          disabled={blocked}
          state={submit.state}
          loadingLabel="Publishing…"
          successLabel="Published"
          errorLabel="Not published"
          onClick={() => {
            setRefusal(null);
            void submit.run();
          }}
        >
          Publish
        </Button>
      </DialogFooter>
    </>
  );
}

function CloseForm({ list, onClose }: { list: PriceList; onClose: () => void }): React.JSX.Element {
  const close = useClosePriceList();
  const idempotency = useIdempotencyKey();
  const today = todayInIndia();
  const [lastDay, setLastDay] = useState(today);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const earliest = list.from > today ? list.from : today;
  const problem = !/^\d{4}-\d{2}-\d{2}$/.test(lastDay)
    ? "Choose its last day."
    : lastDay < earliest
      ? `On ${dayText(earliest)} or later: a list is closed going forward only.`
      : null;

  const submit = useAsyncAction({
    action: () => {
      // The API's end date is exclusive: the first day without the list.
      const request = { listId: list.id, to: shiftCalendarDay(lastDay, 1) };
      return close.mutateAsync({ ...request, idempotencyKey: idempotency.keyFor(request) });
    },
    logger: log,
    fn: "handleClosePriceList",
    dataId: "MSTR-006",
    onSuccess: () => {
      idempotency.reset();
      toast.success(`${list.name} ends after ${dayText(lastDay)}`);
      onClose();
    },
    onError: (error) => {
      const read = readRefusal(error, { effective_to: "to" });
      setRefusal(read.message ?? Object.values(read.fields).join(" "));
    },
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>Close {list.name}</DialogTitle>
        <DialogDescription>
          Quotations stop pricing from it after the day you choose. Its rates stay on record.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <form
          id="close-list-form"
          noValidate
          aria-label="Close the price list"
          className="flex flex-col gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            setShown(true);
            setRefusal(null);
            if (problem !== null) return;
            void submit.run();
          }}
        >
          <Field data-invalid={shown && problem !== null ? true : undefined}>
            <FieldLabel htmlFor="close-last-day">Last day in force</FieldLabel>
            <Input
              id="close-last-day"
              type="date"
              min={earliest}
              value={lastDay}
              aria-invalid={shown && problem !== null ? true : undefined}
              aria-describedby={
                shown && problem !== null ? "close-last-day-error" : "close-last-day-help"
              }
              onChange={(event) => {
                setLastDay(event.target.value);
              }}
            />
            {shown && problem !== null ? null : (
              <FieldDescription id="close-last-day-help">
                Without a list in force, its products can&apos;t be quoted in its scope.
              </FieldDescription>
            )}
            <FieldError id="close-last-day-error">{shown ? problem : null}</FieldError>
          </Field>
          {refusal === null ? null : (
            <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
              {refusal}
            </p>
          )}
        </form>
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          form="close-list-form"
          variant="destructive"
          state={submit.state}
          loadingLabel="Closing…"
          successLabel="Closed"
          errorLabel="Not closed"
        >
          Close the list
        </Button>
      </DialogFooter>
    </>
  );
}

function RateRowsSkeleton(): React.JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading rates"
      className="flex flex-col divide-y divide-border rounded-xl border border-border"
    >
      {Array.from({ length: 6 }, (_, index) => (
        <div key={index} className="flex items-center justify-between gap-4 p-3">
          <Skeleton className="h-4 w-64 max-w-full" />
          <Skeleton className="h-8 w-32" />
        </div>
      ))}
    </div>
  );
}

export function PriceListSheetSkeleton(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-80 max-w-full" />
      </div>
      <RateRowsSkeleton />
    </div>
  );
}
