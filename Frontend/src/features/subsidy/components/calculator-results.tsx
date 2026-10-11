"use client";

import type * as React from "react";

import { Notice } from "@/components/patterns/notice";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type {
  Blocks,
  CategoryResult,
  CropResult,
  SprinklerResult,
  SubsidyCalculation,
  SubsidyCategory,
  SystemConfig,
} from "@/features/subsidy/api/subsidy.schemas";
import { readWarning } from "@/features/subsidy/lib/calculator-draft";
import {
  BLOCK_ROWS,
  ratioAsPercent,
  warningTitle,
  type BlockRow,
} from "@/features/subsidy/lib/subsidy-labels";
import { formatFullDate, formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

function rupees(value: string): string {
  return formatInr(value, { paise: true });
}

function cropName(crop: CropResult, index: number, many: boolean): string {
  const name =
    crop.crop === null
      ? "No crop chosen"
      : crop.interCrop === null
        ? crop.crop
        : `${crop.crop} with ${crop.interCrop}`;
  return many ? `Block ${String(index + 1)} · ${name}` : name;
}

// ── warnings ──────────────────────────────────────────────────────────────────────

interface PlacedWarning {
  readonly key: string;
  readonly where: string | null;
  readonly code: string;
  readonly sentence: string;
}

function collectWarnings(result: SubsidyCalculation): PlacedWarning[] {
  const many = result.crops.length > 1;
  const placed: PlacedWarning[] = result.warnings.map((warning, index) => ({
    key: `all-${String(index)}`,
    where: null,
    ...readWarning(warning),
  }));
  result.crops.forEach((crop, cropIndex) => {
    crop.warnings.forEach((warning, index) => {
      placed.push({
        key: `crop-${String(cropIndex)}-${String(index)}`,
        where: many ? cropName(crop, cropIndex, true) : null,
        ...readWarning(warning),
      });
    });
  });
  return placed;
}

/**
 * SUBS-002 · Where the engine deliberately differs from the scheme's spreadsheet, or clamped a
 * figure. Each names its crop block when there are two, and says what it means.
 */
function CalculationWarnings({ result }: { result: SubsidyCalculation }): React.JSX.Element | null {
  const warnings = collectWarnings(result);
  if (warnings.length === 0) return null;
  return (
    <Notice tone="warning">
      <p className="font-medium">
        {warnings.length === 1 ? "One thing to know" : `${String(warnings.length)} things to know`}
      </p>
      <ul className="flex list-disc flex-col gap-1 pl-4">
        {warnings.map((warning) => {
          const title = warningTitle(warning.code);
          return (
            <li key={warning.key} data-code={warning.code || undefined}>
              {warning.where === null ? null : (
                <span className="text-muted-foreground">{warning.where}: </span>
              )}
              {title === null ? null : <span className="font-medium">{title}. </span>}
              {warning.sentence}
            </li>
          );
        })}
      </ul>
    </Notice>
  );
}

// ── one crop ──────────────────────────────────────────────────────────────────────

function SpacingFacts({ crop }: { crop: CropResult }): React.JSX.Element {
  const raised = crop.spacing.forSubsidy !== crop.spacing.designed;
  const facts = [
    { label: "Designed", value: crop.spacing.designed },
    { label: "Scheme standard", value: crop.spacing.standard },
    { label: "Used for subsidy", value: crop.spacing.forSubsidy, strong: true },
  ];
  return (
    <div className="flex flex-col gap-1.5">
      <dl className="grid grid-cols-3 gap-2">
        {facts.map((fact) => (
          <div
            key={fact.label}
            className={cn(
              "flex flex-col gap-0.5 rounded-md border border-border px-2.5 py-2",
              fact.strong && "bg-muted",
            )}
          >
            <dt className="text-xs text-muted-foreground">{fact.label}</dt>
            <dd
              className={cn("text-sm text-foreground tabular-nums", fact.strong && "font-semibold")}
            >
              {fact.value} m
            </dd>
          </div>
        ))}
      </dl>
      {raised ? (
        <p className="text-xs text-muted-foreground">
          The scheme&apos;s standard is wider than the design, so the subsidy runs at{" "}
          {crop.spacing.forSubsidy} m. A tighter design earns no more.
        </p>
      ) : null}
    </div>
  );
}

function CategoryTable({
  categories,
  caption,
}: {
  categories: readonly CategoryResult[];
  caption: string;
}): React.JSX.Element {
  const hasGsdma = categories.some((row) => row.gsdmaFarmerShare !== null);
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">{caption}</caption>
      <thead>
        <tr className="border-b border-border text-left text-xs text-muted-foreground">
          <th scope="col" className="py-2 pr-3 font-medium">
            Category
          </th>
          <th scope="col" className="py-2 pr-3 text-right font-medium">
            Subsidy
          </th>
          <th scope="col" className="py-2 text-right font-medium">
            Farmer pays
          </th>
        </tr>
      </thead>
      <tbody>
        {categories.map((row) => (
          <tr
            key={row.code}
            data-applicable={row.applicable}
            className={cn(
              "border-b border-border align-top last:border-0",
              !row.applicable && "text-subtle-foreground",
            )}
          >
            <th scope="row" className="py-2 pr-3 text-left font-normal">
              <span className={row.applicable ? "text-foreground" : undefined}>{row.name}</span>
              {row.variant === "seven_year" ? (
                <Badge variant="outline" className="ml-1.5 align-middle">
                  7-year
                </Badge>
              ) : null}
              {row.applicable || row.reason === null ? null : (
                <span className="mt-0.5 block text-xs">{row.reason}</span>
              )}
            </th>
            {row.applicable ? (
              <>
                <td className="py-2 pr-3 text-right tabular-nums">
                  <span className="block font-medium text-foreground">{rupees(row.subsidy)}</span>
                  <span className="block text-xs text-muted-foreground">{row.subsidyPct}%</span>
                </td>
                <td className="py-2 text-right tabular-nums">
                  <span className="block text-foreground">{rupees(row.farmerShare)}</span>
                  {hasGsdma && row.gsdmaFarmerShare !== null ? (
                    <span className="block text-xs text-muted-foreground">
                      With GSDMA {rupees(row.gsdmaFarmerShare)}
                    </span>
                  ) : null}
                </td>
              </>
            ) : (
              <td colSpan={2} className="py-2 text-right text-xs">
                Doesn&apos;t apply
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CropResultCard({
  crop,
  index,
  many,
  stale,
}: {
  crop: CropResult;
  index: number;
  many: boolean;
  stale: boolean;
}): React.JSX.Element {
  const name = cropName(crop, index, many);
  return (
    <Card
      aria-label={name}
      className={cn("transition-opacity duration-fast", stale && "opacity-60")}
    >
      <CardHeader>
        <div className="flex min-w-0 flex-col gap-0.5">
          <CardTitle level={3} className="truncate">
            {name}
          </CardTitle>
          <CardDescription className="tabular-nums">{crop.area} Ha</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <SpacingFacts crop={crop} />
        <dl className="grid gap-2 sm:grid-cols-2">
          <div className="flex flex-col gap-0.5 rounded-md bg-muted px-3 py-2">
            <dt className="text-xs text-muted-foreground">Unit cost the scheme allows</dt>
            <dd className="text-lg font-semibold text-foreground tabular-nums">
              {rupees(crop.unitCostForCap)}
            </dd>
          </div>
          <div className="flex flex-col gap-0.5 rounded-md border border-border px-3 py-2">
            <dt className="text-xs text-muted-foreground">Seven-year unit cost</dt>
            <dd className="text-lg text-foreground tabular-nums">
              {crop.unitCostSevenYear === null ? (
                <span className="text-sm text-muted-foreground">Outside the window</span>
              ) : (
                rupees(crop.unitCostSevenYear)
              )}
            </dd>
          </div>
        </dl>
        <CategoryTable categories={crop.categories} caption={`Farmer categories for ${name}`} />
      </CardContent>
    </Card>
  );
}

// ── the summary ───────────────────────────────────────────────────────────────────

function blockLabel(row: BlockRow, parameters: Readonly<Record<string, string>>): string {
  if (row.rate === undefined) return row.label;
  const rate = ratioAsPercent(parameters[row.rate]);
  return rate === null ? row.label : `${row.label} (${rate})`;
}

/**
 * SUBS-002 · The quotation summary, a column per crop block and the total. Each figure is the
 * backend's, rounded where the scheme's sheet rounds — a column may not visibly add up.
 */
function SummaryTable({
  result,
  hasHeadUnit,
  parameters,
  stale,
}: {
  result: SubsidyCalculation;
  hasHeadUnit: boolean;
  parameters: Readonly<Record<string, string>>;
  stale: boolean;
}): React.JSX.Element {
  const many = result.crops.length > 1;
  const columns: { key: string; label: string; blocks: Blocks }[] = many
    ? [
        ...result.crops.map((crop, index) => ({
          key: `crop-${String(index)}`,
          label: `Block ${String(index + 1)}`,
          blocks: crop.blocks,
        })),
        { key: "total", label: "Total", blocks: result.total },
      ]
    : [{ key: "total", label: "Amount", blocks: result.total }];
  const rows = BLOCK_ROWS.filter((row) => row.key !== "head_unit" || hasHeadUnit);

  return (
    <Card className={cn("transition-opacity duration-fast", stale && "opacity-60")}>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Quotation summary</CardTitle>
          <CardDescription>
            Rounded where the scheme&apos;s sheet rounds, so a column may not add up to the paisa.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {/* Browsers make a scrolling box keyboard-focusable themselves; the region names it. */}
        <div
          role="region"
          aria-label="Quotation summary table"
          className="-mx-5 overflow-x-auto px-5 focus-ring-inset"
        >
          <table className="w-full min-w-max text-sm">
            <caption className="sr-only">Quotation summary</caption>
            <thead>
              <tr className="border-b border-border text-xs text-muted-foreground">
                <th scope="col" className="py-2 pr-4 text-left font-medium">
                  Block
                </th>
                {columns.map((column) => (
                  <th key={column.key} scope="col" className="py-2 pl-4 text-right font-medium">
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.key}
                  className={cn(
                    row.tone === "subtotal" && "border-t border-border",
                    row.tone === "total" && "border-t-2 border-foreground",
                  )}
                >
                  <th
                    scope="row"
                    className={cn(
                      "py-1.5 pr-4 text-left font-normal",
                      row.tone === "tax" && "pl-3 text-muted-foreground",
                      row.tone === "subtotal" && "font-medium text-foreground",
                      row.tone === "total" && "py-2.5 font-semibold text-foreground",
                    )}
                  >
                    {blockLabel(row, parameters)}
                  </th>
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={cn(
                        "py-1.5 pl-4 text-right tabular-nums",
                        row.tone === "tax" ? "text-muted-foreground" : "text-foreground",
                        row.tone === "subtotal" && "font-medium",
                        row.tone === "total" && "py-2.5 text-base font-semibold",
                      )}
                    >
                      {rupees(column.blocks[row.key])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function SprinklerCard({
  sprinkler,
  stale,
}: {
  sprinkler: SprinklerResult;
  stale: boolean;
}): React.JSX.Element {
  return (
    <Card className={cn("transition-opacity duration-fast", stale && "opacity-60")}>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Derived items</CardTitle>
          <CardDescription>
            {sprinkler.pipeSizeMm} mm pipe for this area, {sprinkler.nozzle} nozzles.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ul aria-label="Derived items" className="flex flex-col divide-y divide-border text-sm">
          {sprinkler.lines.map((line) => (
            <li key={line.component} className="flex items-start justify-between gap-3 py-2">
              <span className="flex min-w-0 flex-col">
                <span className="text-foreground">{line.description}</span>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {line.qty} {line.uom} × {rupees(line.rate)}
                </span>
              </span>
              <span className="shrink-0 text-foreground tabular-nums">{rupees(line.amount)}</span>
            </li>
          ))}
        </ul>
        <div className="flex items-baseline justify-between gap-3 border-t border-border pt-3">
          <span className="text-sm text-muted-foreground">DBT farmer payable</span>
          <span className="font-semibold text-foreground tabular-nums">
            {rupees(sprinkler.dbtFarmerPayable)}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

export interface CalculationFiguresProps {
  result: SubsidyCalculation;
  hasHeadUnit: boolean;
  parameters: Readonly<Record<string, string>>;
  /** The figures belong to older inputs: dimmed while the next arrive. */
  stale?: boolean;
  /** A stored calculation says so, instead of "a preview". */
  stored?: boolean;
}

/**
 * SUBS-002, SUBS-006 · A calculation's figures: the warnings, each crop block, Sprinkler's
 * derived items and the summary. The live calculator and an application's stored calculation
 * both print through this.
 */
export function CalculationFigures({
  result,
  hasHeadUnit,
  parameters,
  stale = false,
  stored = false,
}: CalculationFiguresProps): React.JSX.Element {
  return (
    <>
      <CalculationWarnings result={result} />
      {result.crops.map((crop, index) => (
        <CropResultCard
          key={`${String(index)}-${crop.crop ?? ""}`}
          crop={crop}
          index={index}
          many={result.crops.length > 1}
          stale={stale}
        />
      ))}
      {result.sprinkler === null ? null : (
        <SprinklerCard sprinkler={result.sprinkler} stale={stale} />
      )}
      <SummaryTable
        result={result}
        hasHeadUnit={hasHeadUnit}
        parameters={parameters}
        stale={stale}
      />
      <p className="text-xs text-muted-foreground">
        Formula {result.formulaVersion}
        {stored
          ? `, masters of ${formatFullDate(result.asOf)}. Stored when the application started.`
          : ". A preview: nothing is saved."}
      </p>
    </>
  );
}

// ── the panel ─────────────────────────────────────────────────────────────────────

export interface CalculatorResultsProps {
  system: SystemConfig;
  parameters: Readonly<Record<string, string>>;
  result: SubsidyCalculation | null;
  /** The figures on screen belong to the inputs on screen. */
  upToDate: boolean;
  calculating: boolean;
  /** What the panel says while there are no figures, or why the shown ones are old. */
  waitingFor: string | null;
  /** The categories to list before anything is calculated; null while they load. */
  categories: readonly SubsidyCategory[] | null;
  /** Problems no input shows, e.g. too many crop blocks. */
  unplaced: readonly string[];
  failed: React.ReactNode;
  /** Shown under the figures, e.g. the farmer's category when starting an application. */
  after?: React.ReactNode;
}

/**
 * SUBS-002 · What the backend calculated for the inputs beside it: warnings, each crop's
 * spacing, unit cost and eight categories, then the summary. Before anything is calculated it
 * lists the categories, so the designer sees what they will get.
 */
export function CalculatorResults({
  system,
  parameters,
  result,
  upToDate,
  calculating,
  waitingFor,
  categories,
  unplaced,
  failed,
  after = null,
}: CalculatorResultsProps): React.JSX.Element {
  const stale = result !== null && !upToDate;
  const status = calculating
    ? "Calculating…"
    : result !== null && upToDate
      ? `Figures from the masters in force on ${formatFullDate(result.asOf)}.`
      : waitingFor;

  return (
    <section aria-labelledby="results-title" className="flex flex-col gap-4">
      <div className="flex flex-col gap-0.5">
        <h2 id="results-title" className="text-base font-semibold text-foreground">
          Subsidy
        </h2>
        <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
          {status}
        </p>
      </div>

      {unplaced.length > 0 ? (
        <Notice tone="danger">
          {unplaced.map((problem) => (
            <p key={problem}>{problem}</p>
          ))}
        </Notice>
      ) : null}
      {failed}

      {result === null ? (
        <CategoryPreview categories={categories} />
      ) : (
        <CalculationFigures
          result={result}
          hasHeadUnit={system.hasHeadUnit}
          parameters={parameters}
          stale={stale}
        />
      )}
      {after}
    </section>
  );
}

/** The eight categories, named before any figure exists. */
function CategoryPreview({
  categories,
}: {
  categories: readonly SubsidyCategory[] | null;
}): React.JSX.Element {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Farmer categories</CardTitle>
          <CardDescription>Each gets its subsidy and the farmer&apos;s share.</CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        {categories === null ? (
          <div className="flex flex-col gap-3" aria-hidden>
            {Array.from({ length: 8 }, (_, index) => (
              <Skeleton key={index} className="h-5 w-full" />
            ))}
          </div>
        ) : (
          <ul aria-label="Farmer categories" className="flex flex-col divide-y divide-border">
            {categories.map((category) => (
              <li
                key={category.code}
                className="flex items-center justify-between gap-3 py-2 text-sm"
              >
                <span className="text-foreground">
                  {category.name}
                  {category.variant === "seven_year" ? (
                    <Badge variant="outline" className="ml-1.5 align-middle">
                      7-year
                    </Badge>
                  ) : null}
                </span>
                <span className="text-muted-foreground tabular-nums">{category.pct}%</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function CalculatorResultsSkeleton(): React.JSX.Element {
  return (
    <div className="flex flex-col gap-4" aria-hidden>
      <Skeleton className="h-6 w-32" />
      <Skeleton className="h-72 w-full rounded-xl" />
      <Skeleton className="h-96 w-full rounded-xl" />
    </div>
  );
}
