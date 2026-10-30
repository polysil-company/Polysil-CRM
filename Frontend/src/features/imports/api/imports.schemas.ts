import { z } from "zod";

/**
 * MSTR-007 · Excel import with column matching (FS-062). Contract: `backend/docs/api/imports.md`,
 * handover `excel-import.md`. One backend for three screens: partners, a draft price list's
 * rates, and an order's or quotation's lines.
 *
 * Every count and value arrives ready to show: the backend normalises the rows (a mobile as
 * 91XXXXXXXXXX, money with two decimals) and names what it looked up.
 */

export const IMPORT_KINDS = ["partners", "price_list_items", "lines"] as const;
export type ImportKind = (typeof IMPORT_KINDS)[number];

export const IMPORT_STATUSES = ["uploaded", "checked", "committed", "discarded"] as const;

/** `replace`: the file becomes the whole list. `merge`: rates not in the file stay. */
export const IMPORT_MODES = ["replace", "merge"] as const;
export type ImportMode = (typeof IMPORT_MODES)[number];

/** Field key to column index, 0-based into the headers. */
export type ImportMapping = Readonly<Record<string, number>>;

const mappingSchema = z.record(z.string(), z.number().int().nonnegative());

const fieldSchema = z.object({
  key: z.string().min(1),
  label: z.string().min(1),
  required: z.boolean(),
  help: z.string(),
});

export type ImportField = z.output<typeof fieldSchema>;

const lineWireSchema = z.object({
  row: z.number().int(),
  product_id: z.string().min(1),
  product: z.string(),
  qty: z.string(),
  discount_pct: z.string(),
  discount2_pct: z.string(),
  discount3_pct: z.string(),
});

/** A good row of a `lines` import, ready for the line editor. */
export interface ImportLine {
  readonly row: number;
  readonly productId: string;
  readonly product: string;
  readonly qty: string;
  readonly discounts: readonly [string, string, string];
}

const checkWireSchema = z.object({
  total: z.number().int().nonnegative(),
  ok: z.number().int().nonnegative(),
  /** The true count, even when `error_rows` stops at 500. */
  errors: z.number().int().nonnegative(),
  error_rows: z.array(
    z.object({ row: z.number().int(), errors: z.record(z.string(), z.string()) }),
  ),
  preview: z.array(z.object({ row: z.number().int(), values: z.record(z.string(), z.unknown()) })),
  column_warnings: z.record(z.string(), z.string()),
  lines: z.array(lineWireSchema).nullable(),
});

export interface ImportCheck {
  readonly total: number;
  readonly ok: number;
  readonly errors: number;
  /** Each bad row (at most 500), in sheet order: field key to reason. */
  readonly errorRows: readonly { readonly row: number; readonly errors: Record<string, string> }[];
  /** The first 20 good rows as they will be saved: field key to a value to show. */
  readonly preview: readonly { readonly row: number; readonly values: Record<string, string> }[];
  /** Field key to a warning about the whole column. */
  readonly columnWarnings: Readonly<Record<string, string>>;
  /** `lines` imports only: every good row. */
  readonly lines: readonly ImportLine[] | null;
}

/** A preview value as text: the backend sends strings, numbers, booleans and nulls. */
function cellText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

function toCheck(wire: z.output<typeof checkWireSchema>): ImportCheck {
  return {
    total: wire.total,
    ok: wire.ok,
    errors: wire.errors,
    errorRows: wire.error_rows,
    preview: wire.preview.map((row) => ({
      row: row.row,
      values: Object.fromEntries(
        Object.entries(row.values).map(([key, value]) => [key, cellText(value)]),
      ),
    })),
    columnWarnings: wire.column_warnings,
    lines:
      wire.lines?.map((line) => ({
        row: line.row,
        productId: line.product_id,
        product: line.product,
        qty: line.qty,
        discounts: [line.discount_pct, line.discount2_pct, line.discount3_pct],
      })) ?? null,
  };
}

const batchWireSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(IMPORT_KINDS),
  status: z.enum(IMPORT_STATUSES),
  target_id: z.string().nullable(),
  file_name: z.string(),
  /** Null for a CSV. */
  sheet: z.string().nullable(),
  /** Every sheet in the workbook; empty for a CSV. */
  sheets: z.array(z.string()),
  header_row: z.number().int().positive(),
  row_count: z.number().int().nonnegative(),
  headers: z.array(z.string()),
  sample: z.array(z.array(z.string())),
  fields: z.array(fieldSchema),
  suggested_mapping: mappingSchema,
  mapping: mappingSchema.nullable(),
  check: checkWireSchema.nullable(),
  created_at: z.string(),
});

export type ImportBatchWire = z.input<typeof batchWireSchema>;
export type ImportCheckWire = z.input<typeof checkWireSchema>;

export interface ImportBatch {
  readonly id: string;
  readonly kind: ImportKind;
  readonly fileName: string;
  readonly sheet: string | null;
  readonly sheets: readonly string[];
  readonly headerRow: number;
  readonly rowCount: number;
  readonly headers: readonly string[];
  /** The first five rows, cell by cell. */
  readonly sample: readonly (readonly string[])[];
  readonly fields: readonly ImportField[];
  readonly suggestedMapping: ImportMapping;
}

export const importBatchSchema = z
  .object({ data: batchWireSchema })
  .transform(({ data }): ImportBatch => ({
    id: data.id,
    kind: data.kind,
    fileName: data.file_name,
    sheet: data.sheet,
    sheets: data.sheets,
    headerRow: data.header_row,
    rowCount: data.row_count,
    headers: data.headers,
    sample: data.sample,
    fields: data.fields,
    suggestedMapping: data.suggested_mapping,
  }));

export const importCheckSchema = z
  .object({ data: checkWireSchema })
  .transform(({ data }) => toCheck(data));

export const importCommitSchema = z
  .object({
    data: z.object({
      status: z.enum(IMPORT_STATUSES),
      /** Partners created, or rates written. */
      created: z.number().int().nonnegative(),
      skipped: z.number().int().nonnegative(),
      price_list_id: z.string().nullish(),
    }),
  })
  .transform(({ data }) => ({ created: data.created, skipped: data.skipped }));

export type ImportCommitResult = z.output<typeof importCommitSchema>;

/** POST /imports/{id}/check */
export interface ImportCheckRequest {
  readonly mapping: ImportMapping;
  readonly options?: { readonly mode: ImportMode };
}
