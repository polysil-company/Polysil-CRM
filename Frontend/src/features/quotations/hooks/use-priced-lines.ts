"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { quotePreviewQueryOptions } from "@/features/quotations/api/quotations.queries";
import type { QuotePreview, QuoteLinesRequest } from "@/features/quotations/api/quotations.schemas";
import {
  isPriceable,
  lineIssue,
  pricedByKey,
  previewRequestFor,
  routeSaveErrors,
  type DraftLine,
  type PreviewPlan,
  type PricingContext,
} from "@/features/quotations/lib/builder-lines";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { readFieldErrors } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";

/** Price once typing pauses for this long. */
const PREVIEW_DEBOUNCE_MS = 400;

/** A preview request that never goes out: the query is off while there is nothing to price. */
const NOTHING_TO_PRICE: QuoteLinesRequest = { place_of_supply_territory_id: "", lines: [] };

const NO_PLACE: PreviewPlan = { request: null, keys: [] };

export function emptyLine(): DraftLine {
  return { key: createRequestId(), product: null, qty: "", discounts: ["", "", ""] };
}

/** The last preview that belongs to a plan, so rows keep their figures while the next loads. */
export interface PricedSnapshot {
  readonly keys: readonly string[];
  readonly preview: QuotePreview;
}

export interface PricedLines {
  readonly lines: readonly DraftLine[];
  readonly changeLine: (next: DraftLine) => void;
  readonly removeLine: (key: string) => void;
  readonly addLine: () => void;
  /** Refusals from a save, by row key. */
  readonly lineErrors: Readonly<Record<string, string>>;
  readonly setLineErrors: (errors: Readonly<Record<string, string>>) => void;
  /** What is being edited now, and what a save sends. */
  readonly plan: PreviewPlan;
  readonly snapshot: PricedSnapshot | null;
  readonly priced: ReturnType<typeof pricedByKey>;
  readonly totals: QuotePreview["totals"] | null;
  /** A newer plan is waiting for its prices. */
  readonly pricing: boolean;
  /** The figures on screen belong to the lines on screen. */
  readonly upToDate: boolean;
  /** The preview refused a row, by row key. */
  readonly previewErrors: Readonly<Record<string, string>>;
  /** The preview failed for a reason no row explains. */
  readonly previewFailed: boolean;
  readonly preview: UseQueryResult<QuotePreview>;
  readonly rowsWithIssues: number;
  readonly rowsReady: number;
}

/**
 * QUOT-004, SO-005 · The lines of a quotation or an order being built, priced by the backend
 * (`POST /pricing/quote-lines`) as they change, after a pause. The screen prints the figures
 * and never computes them; a save sends what the preview priced.
 */
export function usePricedLines(
  context: PricingContext,
  initialLines: () => DraftLine[],
): PricedLines {
  const [lines, setLines] = useState<DraftLine[]>(initialLines);
  const [lineErrors, setLineErrors] = useState<Readonly<Record<string, string>>>({});

  // Nothing is priced until the screen knows where the goods go (an order typed in afresh).
  const plan = useMemo(
    () => (context.placeOfSupplyTerritoryId === "" ? NO_PLACE : previewRequestFor(lines, context)),
    [lines, context],
  );
  const debouncedPlan = useDebouncedValue(plan, PREVIEW_DEBOUNCE_MS);
  const preview = useQuery({
    ...quotePreviewQueryOptions(debouncedPlan.request ?? NOTHING_TO_PRICE),
    enabled: debouncedPlan.request !== null,
  });

  const [snapshot, setSnapshot] = useState<PricedSnapshot | null>(null);
  if (
    preview.data !== undefined &&
    !preview.isPlaceholderData &&
    snapshot?.preview !== preview.data
  ) {
    setSnapshot({ keys: debouncedPlan.keys, preview: preview.data });
  }
  const upToDate =
    plan.request === null ||
    (debouncedPlan === plan &&
      preview.data !== undefined &&
      !preview.isPlaceholderData &&
      !preview.isFetching);
  const previewErrors =
    preview.isError && debouncedPlan === plan
      ? routeSaveErrors(readFieldErrors(preview.error) ?? {}, debouncedPlan.keys).lines
      : {};

  return {
    lines,
    changeLine: (next) => {
      setLines((current) => current.map((line) => (line.key === next.key ? next : line)));
      setLineErrors(({ [next.key]: _cleared, ...rest }) => rest);
    },
    removeLine: (key) => {
      setLines((current) =>
        current.length === 1 ? [emptyLine()] : current.filter((line) => line.key !== key),
      );
    },
    addLine: () => {
      setLines((current) => [...current, emptyLine()]);
    },
    lineErrors,
    setLineErrors,
    plan,
    snapshot,
    priced: pricedByKey(snapshot?.preview, snapshot?.keys ?? []),
    totals: plan.request === null ? null : (snapshot?.preview.totals ?? null),
    pricing: plan.request !== null && !upToDate && !preview.isError,
    upToDate,
    previewErrors,
    previewFailed:
      preview.isError && debouncedPlan === plan && Object.keys(previewErrors).length === 0,
    preview,
    rowsWithIssues: lines.filter((line) => lineIssue(line) !== null).length,
    rowsReady: lines.filter(isPriceable).length,
  };
}
