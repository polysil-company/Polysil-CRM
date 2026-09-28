"use client";

import { Delete02Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Skeleton } from "@/components/ui/skeleton";
import type { QuotationLine } from "@/features/quotations/api/quotations.schemas";
import { lineIssue, type DraftLine } from "@/features/quotations/lib/builder-lines";
import { formatRate } from "@/features/quotations/lib/quotation-labels";
import { formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ProductPicker } from "./product-picker";

const TIER_LABELS = ["1st disc.", "2nd disc.", "3rd disc."] as const;

export interface QuotationLineRowProps {
  line: DraftLine;
  /** 0-based position; shown as "Item 1". */
  index: number;
  /** The backend's figures for this row, once priced. */
  priced: QuotationLine | undefined;
  /** A preview is on its way. */
  pricing: boolean;
  /** A refusal from the backend for this row. */
  error: string | undefined;
  canRemove: boolean;
  onChange: (next: DraftLine) => void;
  onRemove: () => void;
}

/**
 * QUOT-004 · One item: product, quantity, three discount tiers — each a percentage of the
 * balance after the one before — and, underneath, the figures the backend priced for it.
 */
export function QuotationLineRow({
  line,
  index,
  priced,
  pricing,
  error,
  canRemove,
  onChange,
  onRemove,
}: QuotationLineRowProps): React.JSX.Element {
  const id = `line-${line.key}`;
  const number = index + 1;
  const issue = lineIssue(line);
  const message = error ?? issue;
  const messageId = `${id}-message`;
  const invalid = message === null ? undefined : true;

  return (
    <li
      aria-label={`Item ${String(number)}`}
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border bg-card p-3 sm:p-4",
        error !== undefined && "border-danger",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted-foreground">Item {number}</span>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={`Remove item ${String(number)}`}
          disabled={!canRemove}
          onClick={onRemove}
        >
          <Icon icon={Delete02Icon} />
        </Button>
      </div>

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-12 flex min-w-0 flex-col gap-1.5 md:col-span-6">
          <label htmlFor={`${id}-product`} className="text-xs text-muted-foreground">
            Product
          </label>
          <ProductPicker
            id={`${id}-product`}
            value={line.product}
            aria-invalid={invalid}
            aria-describedby={message === null ? undefined : messageId}
            onValueChange={(product) => {
              onChange({ ...line, product });
            }}
          />
        </div>
        <div className="col-span-12 flex flex-col gap-1.5 sm:col-span-4 md:col-span-2">
          <label htmlFor={`${id}-qty`} className="text-xs text-muted-foreground">
            Quantity
          </label>
          <InputGroup>
            <InputGroupInput
              id={`${id}-qty`}
              inputMode="decimal"
              autoComplete="off"
              value={line.qty}
              aria-invalid={invalid}
              onChange={(event) => {
                onChange({ ...line, qty: event.target.value });
              }}
            />
            {line.product === null ? null : (
              <InputGroupAddon align="end">{line.product.uom}</InputGroupAddon>
            )}
          </InputGroup>
        </div>
        <fieldset className="col-span-12 grid grid-cols-3 gap-2 sm:col-span-8 md:col-span-4">
          <legend className="sr-only">Discounts for item {number}, in order</legend>
          {TIER_LABELS.map((label, tier) => (
            <div key={label} className="flex min-w-0 flex-col gap-1.5">
              <label
                htmlFor={`${id}-discount-${String(tier)}`}
                className="text-xs text-muted-foreground"
              >
                {label}
              </label>
              <InputGroup>
                <InputGroupInput
                  id={`${id}-discount-${String(tier)}`}
                  inputMode="decimal"
                  autoComplete="off"
                  placeholder="0"
                  value={line.discounts[tier] ?? ""}
                  onChange={(event) => {
                    const discounts: [string, string, string] = [...line.discounts];
                    discounts[tier] = event.target.value;
                    onChange({ ...line, discounts });
                  }}
                />
                <InputGroupAddon align="end">%</InputGroupAddon>
              </InputGroup>
            </div>
          ))}
        </fieldset>
      </div>

      <PricedStrip
        priced={priced}
        pricing={pricing}
        ready={issue === null && line.product !== null}
      />
      {message === null ? null : (
        <p
          id={messageId}
          role={error === undefined ? undefined : "alert"}
          className="text-xs text-danger"
        >
          {message}
        </p>
      )}
    </li>
  );
}

/** The backend's figures for the row, or why there are none yet. */
function PricedStrip({
  priced,
  pricing,
  ready,
}: {
  priced: QuotationLine | undefined;
  pricing: boolean;
  ready: boolean;
}): React.JSX.Element | null {
  if (!ready) {
    return null;
  }
  if (priced === undefined) {
    return pricing ? (
      <div role="status" aria-label="Pricing this item" className="flex gap-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-4 w-20" />
      </div>
    ) : null;
  }
  const facts: { label: string; value: string; strong?: boolean }[] = [
    { label: "Rate", value: formatInr(priced.rate, { paise: true }) },
    { label: "Taxable", value: formatInr(priced.taxable, { paise: true }) },
    {
      label: `GST ${formatRate(priced.gstSlab)}`,
      // Printed as the backend split it; the screen never adds money up.
      value:
        Number(priced.igst.amount) > 0
          ? formatInr(priced.igst.amount, { paise: true })
          : `${formatInr(priced.cgst.amount, { paise: true })} + ${formatInr(priced.sgst.amount, { paise: true })}`,
    },
    { label: "Total", value: formatInr(priced.total, { paise: true }), strong: true },
  ];
  return (
    <dl className={cn("flex flex-wrap gap-x-5 gap-y-1 text-xs", pricing && "opacity-60")}>
      {facts.map((fact) => (
        <div key={fact.label} className="flex gap-1.5">
          <dt className="text-muted-foreground">{fact.label}</dt>
          <dd
            className={cn(
              "tabular-nums",
              fact.strong ? "font-semibold text-foreground" : "text-foreground",
            )}
          >
            {fact.value}
          </dd>
        </div>
      ))}
      {priced.provisionalFields.length > 0 ? (
        <div className="text-warning">Indicative rate</div>
      ) : null}
    </dl>
  );
}
