import type { ImportLine } from "@/features/imports/api/imports.schemas";
import {
  takesGstChoice,
  type Freight,
  type FreightRequest,
  type ProductPick,
  type QuotationLine,
  type QuotationLineRequest,
  type QuoteLinesRequest,
  type QuotePreview,
  type TaxTreatment,
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
  /** QUOT-015 · The GST slab picked for this row; null follows the product's HSN. */
  readonly gstSlab: string | null;
}

/** QUOT-015 · The freight box: an amount in rupees ("" for none) and a slab, if one was picked. */
export interface DraftFreight {
  readonly amount: string;
  /** Null takes the default: the highest slab among the lines. */
  readonly gstSlab: string | null;
}

export const NO_FREIGHT: DraftFreight = { amount: "", gstSlab: null };

/** The backend's ceiling on a freight amount, in rupees. */
const MAX_FREIGHT = 99_999_999.99;

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

/** QUOT-015 · Why the freight can't be priced, in words; null when it can or there is none. */
export function freightIssue(freight: DraftFreight): string | null {
  const text = freight.amount.trim();
  if (text === "") {
    return null;
  }
  if (!/^\d+(\.\d{1,2})?$/.test(text) || Number(text) <= 0 || Number(text) > MAX_FREIGHT) {
    return "Rupees above 0, with at most two decimals";
  }
  return null;
}

/** The freight a request carries, or null when the box is empty or not yet valid. */
function freightRequestOf(freight: DraftFreight): FreightRequest | null {
  if (freight.amount.trim() === "" || freightIssue(freight) !== null) {
    return null;
  }
  return {
    amount: freight.amount.trim(),
    ...(freight.gstSlab === null ? {} : { gst_slab: freight.gstSlab }),
  };
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
  /**
   * MSTR-008 · The quotation's sale type or the order's type, so the preview prices from the
   * same lists the save will: a list for that sale type comes before the general ones.
   */
  readonly salesType: string | null;
  /**
   * SO-010 · An export's tax treatment, so the preview shows the tax the document will store.
   * Left out (or domestic) for everything else.
   */
  readonly taxTreatment?: TaxTreatment;
}

/**
 * QUOT-015 · A GST slab per line and freight: commercial and industrial sales, taxed at home.
 * Every other document follows the HSN and takes no freight.
 */
export function allowsGstChoice(
  context: Pick<PricingContext, "salesType" | "taxTreatment">,
): boolean {
  return (
    takesGstChoice(context.salesType) &&
    (context.taxTreatment === undefined || context.taxTreatment === "domestic")
  );
}

/** The pricing request for every row that can be priced; unfinished rows wait. */
export function previewRequestFor(
  lines: readonly DraftLine[],
  context: PricingContext,
  freight: DraftFreight = NO_FREIGHT,
): PreviewPlan {
  const priceable = lines.filter(isPriceable);
  if (priceable.length === 0) {
    return { request: null, keys: [] };
  }
  const choice = allowsGstChoice(context);
  const freightRequest = choice ? freightRequestOf(freight) : null;
  return {
    request: {
      place_of_supply_territory_id: context.placeOfSupplyTerritoryId,
      lines: priceable.map((line) => ({
        product_id: line.product?.id ?? "",
        qty: positiveDecimal(line.qty) ?? "0",
        discount_pct: discountValue(line.discounts[0]) ?? "0",
        discount2_pct: discountValue(line.discounts[1]) ?? "0",
        discount3_pct: discountValue(line.discounts[2]) ?? "0",
        ...(choice && line.gstSlab !== null ? { gst_slab: line.gstSlab } : {}),
      })),
      ...(freightRequest === null ? {} : { freight: freightRequest }),
      ...(context.asOf === null ? {} : { as_of: context.asOf }),
      ...(context.partnerId === null ? {} : { partner_id: context.partnerId }),
      ...(context.salesType === null ? {} : { sales_type: context.salesType }),
      ...(context.taxTreatment === undefined || context.taxTreatment === "domestic"
        ? {}
        : { tax_treatment: context.taxTreatment }),
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

/** QUOT-015 · The freight a save sends: what the preview priced, or null for none. */
export function freightToSave(plan: PreviewPlan): FreightRequest | null {
  return plan.request?.freight ?? null;
}

/** QUOT-015 · The freight box for a saved draft. */
export function draftFreightFrom(freight: Freight | null): DraftFreight {
  return freight === null
    ? NO_FREIGHT
    : {
        amount: trimZeros(freight.amount),
        gstSlab: freight.gstSlabChosen ? trimZeros(freight.gstSlab) : null,
      };
}

/** QUOT-015 · Two slabs are the same rate: "18", "18.0" and "18.000" alike. */
export function sameSlab(a: string, b: string): boolean {
  return Number(a) === Number(b);
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
      gstSlab: line.hsnSlab,
      packMultiple: null,
    },
    qty: trimZeros(line.qty),
    discounts: [
      trimZeros(line.discounts[0].pct),
      trimZeros(line.discounts[1].pct),
      trimZeros(line.discounts[2].pct),
    ],
    // A picked slab is re-sent on every save, or the line falls back to its HSN.
    gstSlab: line.gstSlabChosen ? trimZeros(line.gstSlab) : null,
  }));
}

/**
 * MSTR-007 · The builder's rows for the good rows of an Excel import. The import names each
 * product by id and description only; the unit shows from the price preview, and the backend
 * checks the unit's decimals on save.
 */
export function draftLinesFromImport(
  lines: readonly ImportLine[],
  newKey: () => string,
): DraftLine[] {
  return lines.map((line) => ({
    key: newKey(),
    product: {
      id: line.productId,
      code: null,
      description: line.product,
      uom: "",
      uomDecimals: 3,
      hsnCode: null,
      gstSlab: null,
      packMultiple: null,
    },
    qty: trimZeros(line.qty),
    discounts: [
      trimZeros(line.discounts[0]),
      trimZeros(line.discounts[1]),
      trimZeros(line.discounts[2]),
    ],
    gstSlab: null,
  }));
}

/** "18.000" → "18", "2.500" → "2.5", "0.000" → "0". */
function trimZeros(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

export interface SaveErrors {
  /**
   * Header fields by name: salesType, partyName, partyMobile, partyAddress, partyGstin, terms;
   * on an order also orderType, place, deliveryAddress and remarks.
   */
  readonly header: Readonly<Record<string, string>>;
  /** Row errors by row key. */
  readonly lines: Readonly<Record<string, string>>;
  /** QUOT-015 · A refusal of the freight, its amount or its slab; null when none. */
  readonly freight: string | null;
}

const HEADER_FIELDS: Readonly<Record<string, string>> = {
  sales_type: "salesType",
  export_country: "exportCountry",
  "party.name": "partyName",
  "party.mobile": "partyMobile",
  "party.address": "partyAddress",
  "party.gstin": "partyGstin",
  terms: "terms",
  // An order's header (SO-005).
  party: "partyName",
  order_type: "orderType",
  place_of_supply_territory_id: "place",
  delivery_address: "deliveryAddress",
  remarks: "remarks",
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
  let freight: string | null = null;
  for (const [path, reason] of Object.entries(fields)) {
    const text = sentence(reason);
    const headerField = HEADER_FIELDS[path];
    if (headerField !== undefined) {
      header[headerField] = text;
      continue;
    }
    if (path === "freight" || path.startsWith("freight.")) {
      freight ??= path === "freight.gst_slab" ? `GST: ${lowerFirst(text)}` : text;
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
              : field === "gst_slab"
                ? "GST"
                : "";
      lines[key] ??= label === "" ? text : `${label}: ${lowerFirst(text)}`;
    }
  }
  return { header, lines, freight };
}

function lowerFirst(text: string): string {
  return `${text.charAt(0).toLowerCase()}${text.slice(1)}`;
}

/** The backend's `fields` on any refusal, not only a 422 (a 409 rate_changed carries them too). */
export function readAnyFields(error: { details: unknown }): Record<string, string> {
  const details = error.details;
  if (typeof details !== "object" || details === null || !("fields" in details)) {
    return {};
  }
  const { fields } = details;
  if (typeof fields !== "object" || fields === null) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(fields).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}
