import { z } from "zod";

import { systemTypeSchema, type SystemType } from "./subsidy.schemas";

/**
 * SUBS-012, SUBS-013 · The subsidy masters an administrator revises from a date
 * (`backend/docs/api/subsidy-masters.md`, handover `subsidy-reports-and-masters.md`). A revision
 * starts today or later; calculations dated before it keep the old figures. Figures are decimal
 * strings both ways.
 */

const id = z.string().min(1);
const isoDate = z.iso.date();
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

export const MASTER_KINDS = [
  "categories",
  "parameters",
  "component-rates",
  "crop-spacings",
] as const;
export type MasterKind = (typeof MASTER_KINDS)[number];

/** The units migration 009 knows for a parameter. */
export const PARAMETER_UNITS = ["ratio", "rupees", "hectares", "metres", "flag"] as const;

const windowFields = {
  id,
  effective_from: isoDate,
  /** Null while the row has no end. */
  effective_to: isoDate.nullable(),
};

const categoryRowSchema = z.object({
  ...windowFields,
  system_type: systemTypeSchema,
  code: z.string().min(1),
  name: z.string(),
  pct: decimal,
  variant: z.enum(["regular", "seven_year"]),
  per_ha_cap: decimal.nullable(),
  gsdma_pct: decimal.nullable(),
  sort_order: z.number().int(),
});

const parameterRowSchema = z.object({
  ...windowFields,
  system_type: systemTypeSchema.nullable(),
  key: z.string().min(1),
  value: decimal,
  unit: z.string(),
});

const componentRateRowSchema = z.object({
  ...windowFields,
  system_type: systemTypeSchema,
  component_code: z.string().min(1),
  description: z.string(),
  uom: z.string(),
  pipe_size_mm: z.number().int().nullable(),
  nozzle: z.string().nullable(),
  rate: decimal,
  source_cell: z.string(),
});

const cropSpacingRowSchema = z.object({
  ...windowFields,
  crop: z.string().min(1),
  standard_spacing: decimal,
  sort_order: z.number().int(),
});

export type CategoryRow = z.infer<typeof categoryRowSchema>;
export type ParameterRow = z.infer<typeof parameterRowSchema>;
export type ComponentRateRow = z.infer<typeof componentRateRowSchema>;
export type CropSpacingRow = z.infer<typeof cropSpacingRowSchema>;

/** Each kind's rows, as `GET /subsidy-masters/{kind}` answers. */
export interface MasterRows {
  readonly categories: CategoryRow[];
  readonly parameters: ParameterRow[];
  readonly "component-rates": ComponentRateRow[];
  readonly "crop-spacings": CropSpacingRow[];
}

function envelope<TSchema extends z.ZodType>(
  row: TSchema,
): z.ZodType<z.output<TSchema>[], { data: z.input<TSchema>[] }> {
  return z.object({ data: z.array(row) }).transform(({ data }) => data);
}

/** Typed per kind, so `masterRowsSchemas[kind]` parses to that kind's rows. */
export const masterRowsSchemas: { readonly [K in MasterKind]: z.ZodType<MasterRows[K]> } = {
  categories: envelope(categoryRowSchema),
  parameters: envelope(parameterRowSchema),
  "component-rates": envelope(componentRateRowSchema),
  "crop-spacings": envelope(cropSpacingRowSchema),
};

/** A row as a revision sends it: the table's own shape, without the window. */
export type RevisionRow<K extends MasterKind> = Omit<
  MasterRows[K][number],
  "id" | "effective_from" | "effective_to"
>;

/** POST /subsidy-masters/{kind}/revisions */
export interface RevisionRequest<K extends MasterKind> {
  readonly scheme: string;
  readonly effective_from: string;
  readonly rows: readonly RevisionRow<K>[];
}

export const revisionResultSchema = z
  .object({
    data: z.object({
      closed: z.number().int().nonnegative(),
      inserted: z.number().int().nonnegative(),
      effective_from: isoDate,
    }),
  })
  .transform(({ data }) => ({
    closed: data.closed,
    inserted: data.inserted,
    effectiveFrom: data.effective_from,
  }));

export type RevisionResult = z.output<typeof revisionResultSchema>;

// ── matrices (SUBS-013) ──────────────────────────────────────────────────────────

const unitCostCellSchema = z.object({
  /** Null in a one-dimensional matrix, which has only areas. */
  lateral_spacing: decimal.nullable(),
  area_breakpoint: decimal,
  unit_cost: decimal,
});

const quantityCellSchema = z.object({
  component_code: z.string().min(1),
  area_breakpoint: decimal,
  qty: decimal,
});

export type UnitCostCell = z.infer<typeof unitCostCellSchema>;
export type QuantityCell = z.infer<typeof quantityCellSchema>;

const unitCostMatrixSchema = z.object({
  ...windowFields,
  system_type: systemTypeSchema,
  variant: z.enum(["regular", "seven_year"]),
  dimensionality: z.union([z.literal(1), z.literal(2)]),
  source: z.string().nullable(),
  cells: z.array(unitCostCellSchema),
});

const quantityMatrixSchema = z.object({
  ...windowFields,
  system_type: systemTypeSchema,
  source: z.string().nullable(),
  cells: z.array(quantityCellSchema),
});

export type UnitCostMatrix = z.infer<typeof unitCostMatrixSchema>;
export type QuantityMatrix = z.infer<typeof quantityMatrixSchema>;

export const unitCostMatricesSchema = envelope(unitCostMatrixSchema);
export const quantityMatricesSchema = envelope(quantityMatrixSchema);

/** POST /subsidy-masters/{kind}/matrices — a new matrix with all its cells, from a date. */
export type MatrixRequest =
  | {
      readonly kind: "unit-cost-matrices";
      readonly body: {
        readonly scheme: string;
        readonly system_type: SystemType;
        readonly variant: "regular" | "seven_year";
        readonly dimensionality: 1 | 2;
        readonly effective_from: string;
        readonly source: string;
        readonly unit_cost_cells: readonly UnitCostCell[];
      };
    }
  | {
      readonly kind: "quantity-matrices";
      readonly body: {
        readonly scheme: string;
        readonly system_type: SystemType;
        readonly effective_from: string;
        readonly source: string;
        readonly quantity_cells: readonly QuantityCell[];
      };
    };
