"use client";

import { Add01Icon, DiscountTag01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { QueryView } from "@/components/patterns/query-view";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { PRODUCT_PAGE_SIZE } from "@/features/products/api/products.api";
import { useCopyPriceList, useCreatePriceList } from "@/features/products/api/products.mutations";
import { priceListListQueryOptions } from "@/features/products/api/products.queries";
import {
  CHANNEL_TIERS,
  type ChannelTier,
  type CreatePriceListRequest,
  type PriceList,
} from "@/features/products/api/products.schemas";
import { Pager } from "@/features/products/components/pager";
import {
  PHASE_LABELS,
  phaseOf,
  scopeOf,
  TIER_LABELS,
  windowOf,
  type ListPhase,
} from "@/features/products/lib/product-labels";
import { readRefusal } from "@/features/products/lib/refusals";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatCount, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/products/components/price-lists-panel.tsx",
  dataId: "MSTR-006",
});

const STATUS_FILTERS = ["all", "draft", "published"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];
const STATUS_FILTER_LABELS: Readonly<Record<StatusFilter, string>> = {
  all: "All",
  draft: "Drafts",
  published: "Published",
};

export const PHASE_BADGE: Readonly<Record<ListPhase, BadgeVariant>> = {
  draft: "warning",
  scheduled: "info",
  "in-force": "success",
  ended: "neutral",
};

/** The tier Select's "every tier" choice, since a Select item needs a string value. */
const EVERY_TIER = "every";
const TIER_ITEMS = [
  { value: EVERY_TIER, label: "Every tier" },
  ...CHANNEL_TIERS.map((value) => ({ value, label: TIER_LABELS[value] })),
];

/**
 * MSTR-006 · Price lists: each sets a rate per product for a state and a channel tier (or all
 * of them) from a date. A draft is filled and then published; a published list never changes,
 * and is corrected by starting a new list from it.
 */
export function PriceListsPanel({ canEdit }: { canEdit: boolean }): React.JSX.Element {
  const [status, setStatus] = useState<StatusFilter>("all");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const query = useQuery(priceListListQueryOptions(status === "all" ? null : status, page));

  return (
    <section aria-label="Price lists" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <ToggleGroup
          aria-label="Which price lists"
          value={[status]}
          onValueChange={(next) => {
            const chosen = STATUS_FILTERS.find((value) => value === next[0]);
            if (chosen !== undefined) {
              setStatus(chosen);
              setPage(1);
            }
          }}
        >
          {STATUS_FILTERS.map((value) => (
            <ToggleGroupItem key={value} value={value}>
              {STATUS_FILTER_LABELS[value]}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {canEdit ? (
          <Button
            onClick={() => {
              setCreating(true);
            }}
          >
            <Icon icon={Add01Icon} />
            New price list
          </Button>
        ) : null}
      </div>

      <QueryView
        query={query}
        pending={<PriceListsSkeleton />}
        isEmpty={(data) => data.total === 0}
        empty={
          <EmptyState
            icon={DiscountTag01Icon}
            title={
              status === "draft"
                ? "No drafts"
                : status === "published"
                  ? "Nothing published yet"
                  : "No price lists yet"
            }
            description={
              canEdit
                ? "Start a list, fill in its rates, then publish it: quotations price from it from its start date."
                : "Admin-Sales sets the price lists quotations and orders use."
            }
            className="rounded-xl border border-dashed border-border"
          />
        }
      >
        {(data) => (
          <div className="flex flex-col gap-3">
            <p aria-live="polite" className="text-sm text-muted-foreground">
              {formatCount(data.total)} {data.total === 1 ? "list" : "lists"}, newest first.
            </p>
            <ul aria-label="Price lists" className="flex flex-col gap-2">
              {data.items.map((list) => (
                <PriceListRow key={list.id} list={list} />
              ))}
            </ul>
            <Pager
              page={page}
              limit={PRODUCT_PAGE_SIZE}
              total={data.total}
              noun="lists"
              isPaging={query.isPlaceholderData}
              onPage={setPage}
            />
          </div>
        )}
      </QueryView>

      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent size="md">
          {creating ? (
            <PriceListForm
              source={null}
              onClose={() => {
                setCreating(false);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function PriceListRow({ list }: { list: PriceList }): React.JSX.Element {
  const phase = phaseOf(list);
  return (
    <li>
      <Link
        href={`/products/price-lists/${list.id}`}
        aria-label={`${list.name}, ${PHASE_LABELS[phase]}`}
        transitionTypes={["nav-forward"]}
        className="flex flex-col gap-1.5 rounded-xl border border-border bg-card p-3 transition-colors duration-fast hover:bg-accent sm:p-4"
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold text-foreground">{list.name}</span>
          <Badge variant={PHASE_BADGE[phase]} size="sm" dot>
            {PHASE_LABELS[phase]}
          </Badge>
          {list.provisional ? (
            <Badge variant="warning" size="sm">
              Stand-in rates
            </Badge>
          ) : null}
        </span>
        <span className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
          <span>{scopeOf(list)}</span>
          <span>{windowOf(list.from, list.to)}</span>
          <span className="tabular-nums">
            {formatCount(list.itemCount)} {list.itemCount === 1 ? "rate" : "rates"}
            {list.unpricedCount > 0
              ? ` · ${formatCount(list.unpricedCount)} active without one`
              : ""}
          </span>
        </span>
      </Link>
    </li>
  );
}

/**
 * MSTR-006 · Start a price list: a name, the day it starts, and optionally a state and a tier
 * (empty means every one). With a `source`, the new draft copies its scope and every rate.
 */
export function PriceListForm({
  source,
  onClose,
}: {
  source: PriceList | null;
  onClose: () => void;
}): React.JSX.Element {
  const router = useRouter();
  const create = useCreatePriceList();
  const copy = useCopyPriceList();
  const createKey = useIdempotencyKey();
  const fillKey = useIdempotencyKey();
  const [name, setName] = useState(source === null ? "" : `${source.name} (revised)`);
  const [from, setFrom] = useState(todayInIndia);
  const [state, setState] = useState<TerritoryChoice | null>(null);
  const [tier, setTier] = useState<string>(EVERY_TIER);
  const [note, setNote] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const problems = {
    name: name.trim() === "" ? "Name it so sales staff recognise it." : null,
    from: /^\d{4}-\d{2}-\d{2}$/.test(from) ? null : "Choose the day it starts.",
  };

  const submit = useAsyncAction({
    action: () => {
      const sourceNote = note.trim() === "" ? null : note.trim();
      if (source !== null) {
        const request = { name: name.trim(), from, sourceNote, source: source.id };
        return copy.mutateAsync({
          source,
          name: name.trim(),
          from,
          sourceNote,
          createKey: createKey.keyFor(request),
          fillKey: fillKey.keyFor({ ...request, fill: true }),
        });
      }
      const chosenTier: ChannelTier | null = CHANNEL_TIERS.find((value) => value === tier) ?? null;
      const body: CreatePriceListRequest = {
        name: name.trim(),
        effective_from: from,
        state_territory_id: state?.id ?? null,
        channel_tier: chosenTier,
        effective_to: null,
        source_note: sourceNote,
      };
      return create.mutateAsync({ body, idempotencyKey: createKey.keyFor(body) });
    },
    logger: log,
    fn: source === null ? "handleCreatePriceList" : "handleCopyPriceList",
    dataId: "MSTR-006",
    onSuccess: (draft) => {
      createKey.reset();
      fillKey.reset();
      toast.success("Draft price list started", {
        description:
          source === null
            ? "Fill in its rates, then publish it."
            : "Its rates are copied: change what needs it, then publish.",
      });
      onClose();
      router.push(`/products/price-lists/${draft.id}`);
    },
    onError: (error) => {
      const read = readRefusal(error, { name: "name", effective_from: "from" });
      setRefusal(read.message ?? Object.values(read.fields).join(" "));
    },
  });

  return (
    <>
      <DialogHeader>
        <DialogTitle>
          {source === null ? "New price list" : `New list from ${source.name}`}
        </DialogTitle>
        <DialogDescription>
          {source === null
            ? "It starts as a draft: fill in its rates, then publish it."
            : `Same scope (${scopeOf(source)}) and every rate copied, as a draft to change and publish.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <form
          id="price-list-form"
          noValidate
          aria-label={source === null ? "New price list" : "New list from this one"}
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            setShown(true);
            setRefusal(null);
            if (Object.values(problems).some((problem) => problem !== null)) return;
            void submit.run();
          }}
        >
          <Field data-invalid={shown && problems.name !== null ? true : undefined}>
            <FieldLabel htmlFor="list-name">Name</FieldLabel>
            <Input
              id="list-name"
              autoComplete="off"
              maxLength={120}
              value={name}
              aria-invalid={shown && problems.name !== null ? true : undefined}
              aria-describedby={shown && problems.name !== null ? "list-name-error" : undefined}
              onChange={(event) => {
                setName(event.target.value);
              }}
            />
            <FieldError id="list-name-error">{shown ? problems.name : null}</FieldError>
          </Field>
          <Field data-invalid={shown && problems.from !== null ? true : undefined}>
            <FieldLabel htmlFor="list-from">Starts on</FieldLabel>
            <Input
              id="list-from"
              type="date"
              value={from}
              aria-describedby="list-from-help"
              onChange={(event) => {
                setFrom(event.target.value);
              }}
            />
            <FieldDescription id="list-from-help">
              Publishing it closes the list of the same scope it replaces, the day before.
            </FieldDescription>
            <FieldError>{shown ? problems.from : null}</FieldError>
          </Field>
          {source === null ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="list-state">State (optional)</FieldLabel>
                <TerritoryPicker
                  id="list-state"
                  levels={["state"]}
                  placeholder="Every state"
                  value={state}
                  onValueChange={setState}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="list-tier">Channel tier</FieldLabel>
                <Select
                  items={TIER_ITEMS}
                  value={tier}
                  onValueChange={(next) => {
                    setTier(typeof next === "string" ? next : EVERY_TIER);
                  }}
                >
                  <SelectTrigger id="list-tier" className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TIER_ITEMS.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            </div>
          ) : null}
          <Field>
            <FieldLabel htmlFor="list-note">Where the rates come from (optional)</FieldLabel>
            <Textarea
              id="list-note"
              rows={2}
              maxLength={500}
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
              }}
            />
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
          form="price-list-form"
          state={submit.state}
          loadingLabel="Starting…"
          successLabel="Started"
          errorLabel="Not started"
        >
          Start the draft
        </Button>
      </DialogFooter>
    </>
  );
}

function PriceListsSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading price lists" className="flex flex-col gap-2">
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-xl border border-border p-3 sm:p-4">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-72 max-w-full" />
        </div>
      ))}
    </div>
  );
}
