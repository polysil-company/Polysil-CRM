import type {
  ProductPick,
  QuotationLine,
  QuotationLineRequest,
  QuoteLinesRequest,
  QuotePreview,
} from "@/features/quotations/api/quotations.schemas";

/**
 * QUOT-004, QUOT-005 · The builder's lines, as pure functions: what the user is editing, what
 * goes to the pricing preview, and what a save sends. Decimals stay strings throughout.
 */

/** One row in the builder. `key` is local and stable, so rows keep their state when others go. */
export interface DraftLine {
  readonly key: string;
  readonly product: ProductPick | null;
  readonly qty: string;
  readonly discounts: readonly [string, string, string];
}

const NUMBER_PATTERN = /^\d+(\.\d+)?$/;

/** "", "0", "abc" → null; "18", "2.5" → the trimmed string. */
function positiveDecimal(value: string): string | null {
  const text = value.trim();
  return NUMBER_PATTERN.test(text) && Number(text) > 0 ? text : null;
}

/** A discount box: empty means 0; otherwise 0–100 with at most three decimals. */
function discountValue(value: string): string | null {
  const text = value.trim();
  if (text === "") {
    return "0";
  }
  if (!/^\d+(\.\d{1,3})?$/.test(text) || Number(text) > 100) {
    return null;
  }
  return text;
}

/** Why a row cannot be priced yet, in words; null when it can. An empty row is simply skipped. */
export function lineIssue(line: DraftLine): string | null {
  const empty = line.product === null && line.qty.trim() === "";
  if (empty) {
    return null;
  }
  if (line.product === null) {
    return "Choose a product";
  }
  if (positiveDecimal(line.qty) === null) {
    return "Enter a quantity above 0";
  }
  if (line.discounts.some((discount) => discountValue(discount) === null)) {
    return "Discounts are percentages from 0 to 100";
  }
  return null;
}

/** A row that is complete enough to price. */
export function isPriceable(line: DraftLine): boolean {
  return line.product !== null && lineIssue(line) === null;
}

export interface PreviewPlan {
  /** Null when there is nothing to price yet. */
  readonly request: QuoteLinesRequest | null;
  /** The rows sent, in order: preview line i belongs to row `keys[i]`. */
  readonly keys: readonly string[];
}

export interface PricingContext {
  readonly placeOfSupplyTerritoryId: string;
  /** The lead's partner, whose tier prices the lines; null for a direct sale. */
  readonly partnerId: string | null;
  /** A draft keeps the price date it was made on. */
  readonly asOf: string | null;
}

/** The pricing request for every row that can be priced; unfinished rows wait. */
export function previewRequestFor(
  lines: readonly DraftLine[],
  context: PricingContext,
): PreviewPlan {
  const priceable = lines.filter(isPriceable);
  if (priceable.length === 0) {
    return { request: null, keys: [] };
  }
  return {
    request: {
      place_of_supply_territory_id: context.placeOfSupplyTerritoryId,
      lines: priceable.map((line) => ({
        product_id: line.product?.id ?? "",
        qty: positiveDecimal(line.qty) ?? "0",
        discount_pct: discountValue(line.discounts[0]) ?? "0",
        discount2_pct: discountValue(line.discounts[1]) ?? "0",
        discount3_pct: discountValue(line.discounts[2]) ?? "0",
      })),
      ...(context.asOf === null ? {} : { as_of: context.asOf }),
      ...(context.partnerId === null ? {} : { partner_id: context.partnerId }),
    },
    keys: priceable.map((line) => line.key),
  };
}

/** The priced figures for each row, by its key. */
export function pricedByKey(
  preview: QuotePreview | undefined,
  keys: readonly string[],
): ReadonlyMap<string, QuotationLine> {
  const priced = new Map<string, QuotationLine>();
  if (preview === undefined || preview.lines.length !== keys.length) {
    return priced;
  }
  keys.forEach((key, index) => {
    const line = preview.lines[index];
    if (line !== undefined) {
      priced.set(key, line);
    }
  });
  return priced;
}

/**
 * The lines a save sends: every priceable row with the price list row and tax rate its
 * preview used, so the backend can refuse with `rate_changed` if either moved since.
 */
export function linesToSave(plan: PreviewPlan, preview: QuotePreview): QuotationLineRequest[] {
  return (plan.request?.lines ?? []).map((line, index) => {
    const priced = preview.lines[index];
    return {
      ...line,
      ...(priced === undefined
        ? {}
        : { price_list_item_id: priced.priceListItemId, gst_rate_id: priced.gstRateId }),
    };
  });
}

/** The builder's rows for a saved draft. */
export function draftLinesFrom(lines: readonly QuotationLine[], newKey: () => string): DraftLine[] {
  return lines.map((line) => ({
    key: newKey(),
    product: {
      id: line.productId,
      code: null,
      description: line.description,
      uom: line.uom,
      // Not on a saved line; the backend checks the unit's decimals on save.
      uomDecimals: 3,
      hsnCode: line.hsnCode,
      gstSlab: line.gstSlab,
      packMultiple: null,
    },
    qty: trimZeros(line.qty),
    discounts: [
      trimZeros(line.discounts[0].pct),
      trimZeros(line.discounts[1].pct),
      trimZeros(line.discounts[2].pct),
    ],
  }));
}

/** "18.000" → "18", "2.500" → "2.5", "0.000" → "0". */
function trimZeros(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

export interface SaveErrors {
  /** Header fields by name: salesType, partyName, partyMobile, partyAddress, partyGstin, terms. */
  readonly header: Readonly<Record<string, string>>;
  /** Row errors by row key. */
  readonly lines: Readonly<Record<string, string>>;
}

const HEADER_FIELDS: Readonly<Record<string, string>> = {
  sales_type: "salesType",
  "party.name": "partyName",
  "party.mobile": "partyMobile",
  "party.address": "partyAddress",
  "party.gstin": "partyGstin",
  terms: "terms",
};

const LINE_FIELD_PATTERN = /^lines\[(\d+)\]\.(\w+)$/;

/** "product_inactive: not an active product" → "Not an active product". */
function sentence(reason: string): string {
  const colon = reason.indexOf(":");
  const text = (
    colon > 0 && !reason.slice(0, colon).includes(" ") ? reason.slice(colon + 1) : reason
  ).trim();
  return text === "" ? reason : `${text.charAt(0).toUpperCase()}${text.slice(1)}`;
}

/** The backend's `fields` from a refused save or preview, placed on the header and the rows. */
export function routeSaveErrors(
  fields: Readonly<Record<string, string>>,
  keys: readonly string[],
): SaveErrors {
  const header: Record<string, string> = {};
  const lines: Record<string, string> = {};
  for (const [path, reason] of Object.entries(fields)) {
    const text = sentence(reason);
    const headerField = HEADER_FIELDS[path];
    if (headerField !== undefined) {
      header[headerField] = text;
      continue;
    }
    const match = LINE_FIELD_PATTERN.exec(path);
    const key = match?.[1] === undefined ? undefined : keys[Number(match[1])];
    if (key !== undefined) {
      const field = match?.[2] ?? "";
      const label =
        field === "rate"
          ? "Rate"
          : field === "qty"
            ? "Quantity"
            : field.startsWith("discount")
              ? "Discount"
              : "";
      lines[key] ??=
        label === "" ? text : `${label}: ${text.charAt(0).toLowerCase()}${text.slice(1)}`;
    }
  }
  return { header, lines };
}
