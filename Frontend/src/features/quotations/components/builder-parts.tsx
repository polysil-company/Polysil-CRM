"use client";

import { Add01Icon, FileImportIcon } from "@hugeicons/core-free-icons";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ImportDialog } from "@/features/imports/components/import-dialog";
import type { QuotePreview } from "@/features/quotations/api/quotations.schemas";
import type { PricedLines } from "@/features/quotations/hooks/use-priced-lines";
import { draftLinesFromImport } from "@/features/quotations/lib/builder-lines";
import { formatRate, parseWarnings } from "@/features/quotations/lib/quotation-labels";
import { toUserFacingError } from "@/lib/api/error-messages";
import { createRequestId } from "@/lib/api/request-id";
import { formatCount, formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

import { QuotationLineRow, slabKey, slabOptions } from "./quotation-line-row";

/**
 * QUOT-004, SO-005 · The pieces a quotation and an order builder share: the priced items, the
 * totals, the pricing notes and a labelled text field.
 */

/** The items being built, each priced as it changes, with "Add item" and "Import from Excel". */
export function PricedItemsCard({
  priced,
  importInto,
}: {
  priced: PricedLines;
  /** MSTR-007 · What the imported lines are added to; no import without it. */
  importInto?: "quotation" | "order";
}): React.JSX.Element {
  const [importing, setImporting] = useState(false);
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Items</CardTitle>
          <CardDescription>
            Each discount is a percentage of what is left after the one before.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ol aria-label="Items" className="flex flex-col gap-3">
          {priced.lines.map((line, index) => (
            <QuotationLineRow
              key={line.key}
              line={line}
              index={index}
              priced={priced.priced.get(line.key)}
              pricing={priced.pricing}
              error={priced.lineErrors[line.key] ?? priced.previewErrors[line.key]}
              canRemove={priced.lines.length > 1 || line.product !== null || line.qty !== ""}
              slabChoices={priced.gstChoice ? priced.slabChoices : null}
              onChange={priced.changeLine}
              onRemove={() => {
                priced.removeLine(line.key);
              }}
            />
          ))}
        </ol>
        <div className="flex flex-wrap gap-2">
          <Button type="button" variant="outline" onClick={priced.addLine}>
            <Icon icon={Add01Icon} />
            Add item
          </Button>
          {importInto === undefined ? null : (
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setImporting(true);
              }}
            >
              <Icon icon={FileImportIcon} />
              Import from Excel
            </Button>
          )}
        </div>
        {priced.gstChoice ? <FreightEditor priced={priced} /> : null}
        {importInto === undefined ? null : (
          <ImportDialog
            kind="lines"
            open={importing}
            onOpenChange={setImporting}
            title="Import items from Excel"
            description={`A sheet with a product (item code or description) and a quantity on each row, and up to three discounts. The good rows are added to the ${importInto}, then priced as usual.`}
            noun={{ one: "item", many: "items" }}
            linesAction={`Add to ${importInto}`}
            onLines={(lines) => {
              priced.addLines(draftLinesFromImport(lines, createRequestId));
              toast.success(
                `${formatCount(lines.length)} ${lines.length === 1 ? "item" : "items"} added`,
                { description: "Check them, then save." },
              );
            }}
          />
        )}
      </CardContent>
    </Card>
  );
}

/** The value the freight's slab dropdown uses for "no slab picked". */
const DEFAULT_FREIGHT_SLAB = "default";

/**
 * QUOT-015 · One freight charge before tax, for a commercial or industrial sale. Without a slab
 * it takes the highest among the items; the backend prices it like a line of one.
 */
function FreightEditor({ priced }: { priced: PricedLines }): React.JSX.Element {
  const { freight, freightError, pricedFreight } = priced;
  const errorId = "freight-error";
  const items = [
    { value: DEFAULT_FREIGHT_SLAB, label: "Highest of the items" },
    ...slabOptions(priced.slabChoices, freight.gstSlab).map((slab) => ({
      value: slab,
      label: formatRate(slab),
    })),
  ];
  return (
    <fieldset
      aria-describedby={freightError === null ? undefined : errorId}
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border bg-card p-3 sm:p-4",
        freightError !== null && "border-danger",
      )}
    >
      <legend className="sr-only">Freight</legend>
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-12 flex flex-col gap-1.5 sm:col-span-6">
          <label htmlFor="freight-amount" className="text-xs text-muted-foreground">
            Freight before tax (optional)
          </label>
          <InputGroup>
            <InputGroupAddon align="start">₹</InputGroupAddon>
            <InputGroupInput
              id="freight-amount"
              inputMode="decimal"
              autoComplete="off"
              placeholder="0"
              value={freight.amount}
              aria-invalid={freightError === null ? undefined : true}
              onChange={(event) => {
                priced.setFreight({ ...freight, amount: event.target.value });
              }}
            />
          </InputGroup>
        </div>
        <div className="col-span-12 flex flex-col gap-1.5 sm:col-span-6">
          <label htmlFor="freight-gst" className="text-xs text-muted-foreground">
            GST on freight
          </label>
          <Select
            items={items}
            value={freight.gstSlab === null ? DEFAULT_FREIGHT_SLAB : slabKey(freight.gstSlab)}
            onValueChange={(next) => {
              if (next === null) return;
              priced.setFreight({
                ...freight,
                gstSlab: next === DEFAULT_FREIGHT_SLAB ? null : next,
              });
            }}
          >
            <SelectTrigger id="freight-gst">
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
        </div>
      </div>
      {pricedFreight === null ? null : (
        <p className={cn("text-xs text-foreground tabular-nums", priced.pricing && "opacity-60")}>
          GST {formatRate(pricedFreight.gstSlab)}
          {pricedFreight.gstSlabChosen ? "" : " (highest of the items)"}:{" "}
          {Number(pricedFreight.igst.amount) > 0
            ? formatInr(pricedFreight.igst.amount, { paise: true })
            : `${formatInr(pricedFreight.cgst.amount, { paise: true })} + ${formatInr(pricedFreight.sgst.amount, { paise: true })}`}{" "}
          · Freight total {formatInr(pricedFreight.total, { paise: true })}
        </p>
      )}
      {freightError === null ? null : (
        <p id={errorId} role="alert" className="text-xs text-danger">
          {freightError}
        </p>
      )}
    </fieldset>
  );
}

/** The totals, a pricing failure with "Price again", and the pricing notes. */
export function PricedSummary({ priced }: { priced: PricedLines }): React.JSX.Element {
  return (
    <>
      <BuilderTotals
        totals={priced.totals}
        intraState={priced.snapshot?.preview.intraState ?? true}
        stale={priced.pricing}
      />
      {priced.previewFailed ? (
        <div role="alert" className="flex flex-col gap-2 rounded-md bg-danger-soft p-3 text-sm">
          <p className="font-medium text-danger">{toUserFacingError(priced.preview.error).title}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="self-start"
            onClick={() => void priced.preview.refetch()}
          >
            Price again
          </Button>
        </div>
      ) : null}
      <BuilderWarnings warnings={priced.snapshot?.preview.warnings ?? []} />
    </>
  );
}

/** "Add an item to see prices." / "Pricing…" / where the prices come from. */
export function pricingStatus(priced: PricedLines): string {
  return priced.rowsReady === 0
    ? "Add an item to see prices."
    : priced.pricing
      ? "Pricing…"
      : "Priced by the price list in force.";
}

/** Why save is off, in words; null when it isn't. */
export function saveBlocker(priced: PricedLines): string | null {
  if (priced.rowsWithIssues > 0) {
    return `Finish ${priced.rowsWithIssues === 1 ? "one item" : `${String(priced.rowsWithIssues)} items`} first.`;
  }
  if (priced.pricing) return "Pricing…";
  if (priced.previewFailed || Object.keys(priced.previewErrors).length > 0) {
    return "Fix the pricing first.";
  }
  if (priced.freightBlocks) return "Fix the freight first.";
  return null;
}

export interface FieldAria {
  id: string;
  "aria-invalid": true | undefined;
  "aria-describedby": string | undefined;
}

export function TextField({
  id,
  label,
  optional = false,
  error,
  description,
  className,
  children,
}: {
  id: string;
  label: string;
  optional?: boolean;
  error: string | undefined;
  description?: string;
  className?: string;
  children: (aria: FieldAria) => React.ReactNode;
}): React.JSX.Element {
  const errorId = `${id}-error`;
  const descriptionId = `${id}-description`;
  return (
    <Field data-invalid={error ? true : undefined} className={className}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
      </FieldLabel>
      {children({
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error ? errorId : description ? descriptionId : undefined,
      })}
      {description && !error ? (
        <FieldDescription id={descriptionId}>{description}</FieldDescription>
      ) : null}
      <FieldError id={errorId}>{error}</FieldError>
    </Field>
  );
}

function BuilderTotals({
  totals,
  intraState,
  stale,
}: {
  totals: QuotePreview["totals"] | null;
  intraState: boolean;
  stale: boolean;
}): React.JSX.Element {
  const rows: { label: string; value: string | null; strong?: boolean }[] = [
    { label: "Gross", value: totals?.gross ?? null },
    { label: "Discount", value: totals?.discount ?? null },
    // QUOT-015 · Freight sits inside the taxable value, never in gross or discount.
    ...(totals !== null && Number(totals.freight) > 0
      ? [{ label: "Freight", value: totals.freight }]
      : []),
    { label: "Taxable value", value: totals?.taxable ?? null },
    ...(intraState
      ? [
          { label: "CGST", value: totals?.cgst ?? null },
          { label: "SGST", value: totals?.sgst ?? null },
        ]
      : [{ label: "IGST", value: totals?.igst ?? null }]),
    { label: "Total", value: totals?.total ?? null, strong: true },
  ];
  return (
    <dl
      aria-label="Totals"
      className={cn(
        "grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm transition-opacity duration-fast",
        stale && "opacity-60",
      )}
    >
      {rows.map((row) => (
        <div
          key={row.label}
          className={cn(
            "col-span-2 grid grid-cols-subgrid",
            row.strong && "border-t border-border pt-2",
          )}
        >
          <dt className={row.strong ? "font-semibold text-foreground" : "text-muted-foreground"}>
            {row.label}
          </dt>
          <dd
            className={cn(
              "text-right tabular-nums",
              row.strong ? "text-base font-semibold" : "text-foreground",
            )}
          >
            {row.value === null
              ? "—"
              : `${row.label === "Discount" && Number(row.value) !== 0 ? "−" : ""}${formatInr(row.value, { paise: true })}`}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function BuilderWarnings({ warnings }: { warnings: readonly string[] }): React.JSX.Element | null {
  const parsed = parseWarnings(warnings);
  if (parsed.length === 0) {
    return null;
  }
  return (
    <ul aria-label="Pricing notes" className="flex flex-col gap-1.5">
      {parsed.map((warning, index) => (
        <li
          key={`${warning.code}-${String(index)}`}
          className="rounded-md bg-warning-soft px-3 py-2 text-xs text-foreground"
        >
          {warning.code === "provisional_pricing" ? "Indicative pricing: " : null}
          {warning.message}
        </li>
      ))}
    </ul>
  );
}
