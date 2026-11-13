"use client";

import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  gstSlabChoicesQueryOptions,
  quotePreviewQueryOptions,
} from "@/features/quotations/api/quotations.queries";
import type { QuotePreview, QuoteLinesRequest } from "@/features/quotations/api/quotations.schemas";
import {
  allowsGstChoice,
  CHARGE_KINDS,
  chargeIssue,
  isPriceable,
  lineIssue,
  NO_CHARGES,
  pricedByKey,
  previewRequestFor,
  routeSaveErrors,
  type ChargeKind,
  type DraftCharges,
  type DraftFreight,
  type DraftLine,
  type PerCharge,
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

const NO_CHOICES: readonly string[] = [];

const NO_CHARGE_ERRORS: PerCharge<string | null> = {
  freight: null,
  installation: null,
  fittings: null,
};

export function emptyLine(): DraftLine {
  return { key: createRequestId(), product: null, qty: "", discounts: ["", "", ""], gstSlab: null };
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
  /** MSTR-007 · Rows from an Excel import, after the rows already filled in. */
  readonly addLines: (next: readonly DraftLine[]) => void;
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
  /** QUOT-015 · A GST slab per line and the charges are on offer for this sale. */
  readonly gstChoice: boolean;
  /** QUOT-015 · The slabs the dropdowns offer, besides each line's own HSN slab. */
  readonly slabChoices: readonly string[];
  /** QUOT-015, QUOT-016 · Transportation (freight), installation and fittings, as typed. */
  readonly charges: DraftCharges;
  readonly setCharge: (kind: ChargeKind, next: DraftFreight) => void;
  /** Why each charge can't go, in words: typed wrong, refused by a save or the preview. */
  readonly chargeErrors: PerCharge<string | null>;
  /** A charge must change before a save. */
  readonly chargesBlock: boolean;
  readonly setChargeSaveErrors: (errors: PerCharge<string | null>) => void;
  /** Each charge as the preview priced it; null when it has none. */
  readonly pricedCharges: PerCharge<QuotePreview["freight"]>;
}

/**
 * QUOT-004, SO-005 · The lines of a quotation or an order being built, priced by the backend
 * (`POST /pricing/quote-lines`) as they change, after a pause. The screen prints the figures
 * and never computes them; a save sends what the preview priced.
 */
export function usePricedLines(
  context: PricingContext,
  initialLines: () => DraftLine[],
  initialCharges: DraftCharges = NO_CHARGES,
): PricedLines {
  const [lines, setLines] = useState<DraftLine[]>(initialLines);
  const [lineErrors, setLineErrors] = useState<Readonly<Record<string, string>>>({});
  const [charges, setCharges] = useState<DraftCharges>(initialCharges);
  const [chargeSaveErrors, setChargeSaveErrors] =
    useState<PerCharge<string | null>>(NO_CHARGE_ERRORS);
  const gstChoice = allowsGstChoice(context);
  const slabChoices = useQuery({ ...gstSlabChoicesQueryOptions(), enabled: gstChoice });

  // Nothing is priced until the screen knows where the goods go (an order typed in afresh).
  const plan = useMemo(
    () =>
      context.placeOfSupplyTerritoryId === ""
        ? NO_PLACE
        : previewRequestFor(lines, context, charges),
    [lines, context, charges],
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
  const previewRefusal =
    preview.isError && debouncedPlan === plan
      ? routeSaveErrors(readFieldErrors(preview.error) ?? {}, debouncedPlan.keys)
      : null;
  const previewErrors = previewRefusal?.lines ?? {};
  const rowsReady = lines.filter(isPriceable).length;
  // Per charge: what must be fixed before a save, then what a save or the preview refused.
  const blockOf = (kind: ChargeKind): string | null => {
    const charge = charges[kind];
    return (
      (gstChoice ? chargeIssue(charge) : null) ??
      (gstChoice && charge.amount.trim() !== "" && rowsReady === 0 ? "Add an item first" : null) ??
      previewRefusal?.charges[kind] ??
      null
    );
  };
  const chargeBlocks: PerCharge<string | null> = {
    freight: blockOf("freight"),
    installation: blockOf("installation"),
    fittings: blockOf("fittings"),
  };
  const pricedChargeOf = (kind: ChargeKind): QuotePreview["freight"] =>
    plan.request?.[kind] === undefined ? null : (snapshot?.preview[kind] ?? null);

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
    addLines: (next) => {
      if (next.length === 0) return;
      // An untouched empty row gives way to the imported ones.
      setLines((current) => [
        ...current.filter((line) => line.product !== null || line.qty.trim() !== ""),
        ...next,
      ]);
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
      previewRefusal !== null &&
      Object.keys(previewErrors).length === 0 &&
      CHARGE_KINDS.every((kind) => previewRefusal.charges[kind] === null),
    preview,
    rowsWithIssues: lines.filter((line) => lineIssue(line) !== null).length,
    rowsReady,
    gstChoice,
    slabChoices: slabChoices.data ?? NO_CHOICES,
    charges,
    setCharge: (kind, next) => {
      setCharges((current) => ({ ...current, [kind]: next }));
      setChargeSaveErrors((current) => ({ ...current, [kind]: null }));
    },
    chargeErrors: {
      freight: chargeBlocks.freight ?? chargeSaveErrors.freight,
      installation: chargeBlocks.installation ?? chargeSaveErrors.installation,
      fittings: chargeBlocks.fittings ?? chargeSaveErrors.fittings,
    },
    chargesBlock: CHARGE_KINDS.some((kind) => chargeBlocks[kind] !== null),
    setChargeSaveErrors,
    pricedCharges: {
      freight: pricedChargeOf("freight"),
      installation: pricedChargeOf("installation"),
      fittings: pricedChargeOf("fittings"),
    },
  };
}
