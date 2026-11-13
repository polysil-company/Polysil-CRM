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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ImportDialog } from "@/features/imports/components/import-dialog";
import type { QuotePreview } from "@/features/quotations/api/quotations.schemas";
import type { PricedLines } from "@/features/quotations/hooks/use-priced-lines";
import {
  CHARGE_KINDS,
  draftLinesFromImport,
  type ChargeKind,
  type PerCharge,
} from "@/features/quotations/lib/builder-lines";
import {
  CHARGE_LABELS,
  formatRate,
  parseWarnings,
} from "@/features/quotations/lib/quotation-labels";
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
        {priced.gstChoice ? <ChargesEditor priced={priced} /> : null}
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

/** The value a charge's slab dropdown uses for "no slab picked". */
const DEFAULT_CHARGE_SLAB = "default";

/**
 * QUOT-015, QUOT-016 · The charges before tax on a commercial or industrial sale:
 * transportation (the API's freight), installation and fittings material (FS-069, FS-088).
 * Each is optional; the backend prices each like a line of one.
 */
function ChargesEditor({ priced }: { priced: PricedLines }): React.JSX.Element {
  return (
    <fieldset className="flex flex-col gap-3 rounded-lg border border-border bg-card p-3 sm:p-4">
      <legend className="sr-only">Other charges</legend>
      <div className="flex flex-col gap-0.5">
        <p className="text-sm font-medium text-foreground">Other charges</p>
        <p className="text-xs text-muted-foreground">
          Optional, before tax. Each is taxed on its own and added to the taxable value, never to
          the discount.
        </p>
      </div>
      <div className="flex flex-col divide-y divide-border">
        {CHARGE_KINDS.map((kind) => (
          <ChargeRow key={kind} kind={kind} priced={priced} />
        ))}
      </div>
    </fieldset>
  );
}

/** One charge: its amount, the GST on it, and what the preview priced. */
function ChargeRow({ kind, priced }: { kind: ChargeKind; priced: PricedLines }): React.JSX.Element {
  const charge = priced.charges[kind];
  const error = priced.chargeErrors[kind];
  const pricedCharge = priced.pricedCharges[kind];
  const label = CHARGE_LABELS[kind];
  const errorId = `${kind}-error`;
  const items = [
    { value: DEFAULT_CHARGE_SLAB, label: label.defaultSlab },
    ...slabOptions(priced.slabChoices, charge.gstSlab).map((slab) => ({
      value: slab,
      label: formatRate(slab),
    })),
  ];
  return (
    <div className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-12 flex flex-col gap-1.5 sm:col-span-6">
          <label htmlFor={`${kind}-amount`} className="text-xs text-muted-foreground">
            {label.name} before tax (optional)
          </label>
          <InputGroup>
            <InputGroupAddon align="start">₹</InputGroupAddon>
            <InputGroupInput
              id={`${kind}-amount`}
              inputMode="decimal"
              autoComplete="off"
              placeholder="0"
              value={charge.amount}
              aria-invalid={error === null ? undefined : true}
              aria-describedby={error === null ? undefined : errorId}
              onChange={(event) => {
                priced.setCharge(kind, { ...charge, amount: event.target.value });
              }}
            />
          </InputGroup>
        </div>
        <div className="col-span-12 flex flex-col gap-1.5 sm:col-span-6">
          <label htmlFor={`${kind}-gst`} className="text-xs text-muted-foreground">
            GST on {label.name.toLowerCase()}
          </label>
          <Select
            items={items}
            value={charge.gstSlab === null ? DEFAULT_CHARGE_SLAB : slabKey(charge.gstSlab)}
            onValueChange={(next) => {
              if (next === null) return;
              priced.setCharge(kind, {
                ...charge,
                gstSlab: next === DEFAULT_CHARGE_SLAB ? null : next,
              });
            }}
          >
            <SelectTrigger id={`${kind}-gst`}>
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
      {pricedCharge === null ? null : (
        <p className={cn("text-xs text-foreground tabular-nums", priced.pricing && "opacity-60")}>
          GST {formatRate(pricedCharge.gstSlab)}
          {pricedCharge.gstSlabChosen ? "" : ` (${label.defaultNote})`}:{" "}
          {Number(pricedCharge.igst.amount) > 0
            ? formatInr(pricedCharge.igst.amount, { paise: true })
            : `${formatInr(pricedCharge.cgst.amount, { paise: true })} + ${formatInr(pricedCharge.sgst.amount, { paise: true })}`}{" "}
          · {label.name} total {formatInr(pricedCharge.total, { paise: true })}
        </p>
      )}
      {error === null ? null : (
        <p id={errorId} role="alert" className="text-xs text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/** The totals, a pricing failure with "Price again", and the pricing notes. */
export function PricedSummary({ priced }: { priced: PricedLines }): React.JSX.Element {
  return (
    <>
      <BuilderTotals
        totals={priced.totals}
        chargeAmounts={{
          freight: priced.snapshot?.preview.freight?.amount ?? null,
          installation: priced.snapshot?.preview.installation?.amount ?? null,
          fittings: priced.snapshot?.preview.fittings?.amount ?? null,
        }}
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
  if (priced.chargesBlock) return "Fix the other charges first.";
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
  chargeAmounts,
  intraState,
  stale,
}: {
  totals: QuotePreview["totals"] | null;
  /**
   * APP-009 (live test Y-03) · Each priced charge before tax. The backend returns them beside
   * the totals (`freight.amount`), not inside them, so `totals.freight` is only the mock's.
   */
  chargeAmounts: PerCharge<string | null>;
  intraState: boolean;
  stale: boolean;
}): React.JSX.Element {
  // QUOT-015, QUOT-016 · Charges sit inside the taxable value, never in gross or discount.
  const chargeRows = CHARGE_KINDS.flatMap((kind) => {
    const amount = chargeAmounts[kind] ?? totals?.[kind] ?? null;
    return amount !== null && Number(amount) > 0
      ? [{ label: CHARGE_LABELS[kind].name, value: amount }]
      : [];
  });
  const rows: { label: string; value: string | null; strong?: boolean }[] = [
    { label: "Gross", value: totals?.gross ?? null },
    { label: "Discount", value: totals?.discount ?? null },
    ...chargeRows,
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
