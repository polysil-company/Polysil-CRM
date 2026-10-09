import { z } from "zod";

/**
 * SUBS-002, SUBS-003 · The subsidy calculation and its lookups, as the backend serves them
 * (`backend/docs/api/subsidy.md`, handover `subsidy-calculation.md`).
 *
 * Money, areas and unit costs cross the wire as decimal strings — money at two places, areas at
 * three, unit costs at four — and are printed as they come. The screen never adds, rounds or
 * "checks" them: a column may not visibly add up, because the engine rounds only where the
 * scheme's own workbook rounds.
 */

/** A plain decimal string: "199818.16", "0.400", "-0.01". */
const decimal = z.string().regex(/^-?\d+(\.\d+)?$/);

export const SYSTEM_TYPES = ["drip", "mini_sprinkler", "sprinkler"] as const;
export const systemTypeSchema = z.enum(SYSTEM_TYPES);
export type SystemType = z.infer<typeof systemTypeSchema>;

export const NOZZLES = ["plastic", "brass"] as const;
export type Nozzle = (typeof NOZZLES)[number];

const variantSchema = z.enum(["regular", "seven_year"]);

// ── the lookups (SUBS-003) ───────────────────────────────────────────────────────

const systemConfigWireSchema = z.object({
  system_type: systemTypeSchema,
  has_head_unit: z.boolean(),
  supports_group: z.boolean(),
  crop_count_max: z.number().int().positive(),
  spacing_rule: z.string(),
  seven_year_spacing_floor: decimal.nullable(),
  quantity_source: z.string(),
  formula_version: z.string(),
  /** The tabulated areas a Sprinkler quotation may use; null for the other two systems. */
  sprinkler_areas: z.array(decimal).nullable(),
});

const systemConfigSchema = systemConfigWireSchema.transform((wire) => ({
  systemType: wire.system_type,
  hasHeadUnit: wire.has_head_unit,
  supportsGroup: wire.supports_group,
  cropCountMax: wire.crop_count_max,
  formulaVersion: wire.formula_version,
  sprinklerAreas: wire.sprinkler_areas,
}));

export type SystemConfig = z.output<typeof systemConfigSchema>;

export const subsidyConfigSchema = z
  .object({
    data: z.object({
      scheme: z.string().min(1),
      as_of: z.iso.date(),
      systems: z.array(systemConfigSchema),
      /** The constants behind the sums, e.g. `insurance_rate` "0.0028". */
      parameters: z.record(z.string(), z.string()),
    }),
  })
  .transform(({ data }) => ({
    scheme: data.scheme,
    asOf: data.as_of,
    systems: data.systems,
    parameters: data.parameters,
  }));

export type SubsidyConfig = z.output<typeof subsidyConfigSchema>;

export const subsidyCropsSchema = z
  .object({
    data: z.array(z.object({ crop: z.string().min(1), standard_spacing: decimal })),
  })
  .transform(({ data }) =>
    data.map((row) => ({ crop: row.crop, standardSpacing: row.standard_spacing })),
  );

export type SubsidyCrop = z.output<typeof subsidyCropsSchema>[number];

export const subsidyCategoriesSchema = z
  .object({
    data: z.array(
      z.object({
        code: z.string().min(1),
        name: z.string(),
        pct: decimal,
        variant: variantSchema,
        gsdma_pct: decimal.nullable(),
      }),
    ),
  })
  .transform(({ data }) =>
    data.map((row) => ({
      code: row.code,
      name: row.name,
      pct: row.pct,
      variant: row.variant,
      gsdmaPct: row.gsdma_pct,
    })),
  );

export type SubsidyCategory = z.output<typeof subsidyCategoriesSchema>[number];

// ── the calculation (SUBS-002) ───────────────────────────────────────────────────

/** One bill-of-quantities row, as the designer typed it. Rate ≤ 2 decimals, qty ≤ 3. */
export interface SubsidyLineRequest {
  readonly description: string;
  readonly uom: string;
  readonly rate: string;
  readonly qty: string;
}

export interface SubsidyCropRequest {
  /** Exactly as `GET /subsidy/crops` returned it; null means no crop chosen. */
  readonly crop: string | null;
  /** When present it, not the main crop, sets the standard spacing. */
  readonly inter_crop: string | null;
  /** Hectares, at most three decimals. */
  readonly area: string;
  /** Free text such as "1.37 x 0.50", echoed on the document. */
  readonly crop_spacing: string;
  /** The designed lateral spacing in metres. */
  readonly lateral_spacing: string;
  /** Field-unit lines; none for Sprinkler, which derives its own. */
  readonly lines: readonly SubsidyLineRequest[];
}

/** POST /subsidy/calculate. Keys a system doesn't take are left out, not sent empty. */
export interface CalculateRequest {
  /** The scheme's code; left out, the backend uses GGRC. An application sends its lead's. */
  readonly scheme?: string;
  readonly system_type: SystemType;
  readonly crops: readonly SubsidyCropRequest[];
  readonly head_lines?: readonly SubsidyLineRequest[];
  readonly sump?: { readonly rate_per_ha: string };
  readonly group_total_area?: string;
  readonly installation_rate_per_ha?: string;
  readonly nozzle?: Nozzle;
}

/** The 22 rows of the quotation summary, top to bottom. Every key is always present. */
export const BLOCK_KEYS = [
  "head_unit",
  "field_unit",
  "a_plus_b",
  "cgst_ab",
  "sgst_ab",
  "installation",
  "cgst_c",
  "sgst_c",
  "total_abc_gst",
  "insurance",
  "cgst_d",
  "sgst_d",
  "inspection",
  "cgst_e",
  "sgst_e",
  "education",
  "sump",
  "cost_excl_gst",
  "total_cgst",
  "total_sgst",
  "total_gst",
  "total_incl_gst",
] as const;

export type BlockKey = (typeof BLOCK_KEYS)[number];

const blocksSchema = z.object({
  head_unit: decimal,
  field_unit: decimal,
  a_plus_b: decimal,
  cgst_ab: decimal,
  sgst_ab: decimal,
  installation: decimal,
  cgst_c: decimal,
  sgst_c: decimal,
  total_abc_gst: decimal,
  insurance: decimal,
  cgst_d: decimal,
  sgst_d: decimal,
  inspection: decimal,
  cgst_e: decimal,
  sgst_e: decimal,
  education: decimal,
  sump: decimal,
  cost_excl_gst: decimal,
  total_cgst: decimal,
  total_sgst: decimal,
  total_gst: decimal,
  total_incl_gst: decimal,
}) satisfies z.ZodType<Record<BlockKey, string>>;

export type Blocks = z.infer<typeof blocksSchema>;

const categoryResultWireSchema = z.object({
  code: z.string().min(1),
  name: z.string(),
  pct: decimal,
  variant: variantSchema,
  applicable: z.boolean(),
  /** Why the row does not apply; null when it does. */
  reason: z.string().nullable(),
  subsidy: decimal,
  farmer_share: decimal,
  subsidy_pct: decimal,
  /** Mini Sprinkler up to 2 Ha only. */
  gsdma_farmer_share: decimal.nullable(),
});

const categoryResultSchema = categoryResultWireSchema.transform((wire) => ({
  code: wire.code,
  name: wire.name,
  pct: wire.pct,
  variant: wire.variant,
  applicable: wire.applicable,
  reason: wire.reason,
  subsidy: wire.subsidy,
  farmerShare: wire.farmer_share,
  subsidyPct: wire.subsidy_pct,
  gsdmaFarmerShare: wire.gsdma_farmer_share,
}));

export type CategoryResult = z.output<typeof categoryResultSchema>;

const cropResultWireSchema = z.object({
  crop: z.string().nullable(),
  inter_crop: z.string().nullable(),
  area: decimal,
  lateral_spacing_designed: decimal,
  lateral_spacing_standard: decimal,
  lateral_spacing_for_subsidy: decimal,
  blocks: blocksSchema,
  jantri: z.object({
    regular: decimal,
    regular_with_sump: decimal,
    /** What the subsidy is actually capped on — the figure the scheme's own sheet prints. */
    regular_for_cap: decimal,
    seven_year: decimal.nullable(),
  }),
  categories: z.array(categoryResultSchema),
  warnings: z.array(z.string()),
});

const cropResultSchema = cropResultWireSchema.transform((wire) => ({
  crop: wire.crop,
  interCrop: wire.inter_crop,
  area: wire.area,
  spacing: {
    designed: wire.lateral_spacing_designed,
    standard: wire.lateral_spacing_standard,
    forSubsidy: wire.lateral_spacing_for_subsidy,
  },
  blocks: wire.blocks,
  unitCostForCap: wire.jantri.regular_for_cap,
  unitCostSevenYear: wire.jantri.seven_year,
  categories: wire.categories,
  warnings: wire.warnings,
}));

export type CropResult = z.output<typeof cropResultSchema>;

const sprinklerResultSchema = z
  .object({
    /** 75 up to 2.0 Ha, 90 from 2.01; follows the area, never sent. */
    pipe_size_mm: z.number().int().positive(),
    nozzle: z.enum(NOZZLES),
    lines: z.array(
      z.object({
        component: z.string(),
        description: z.string(),
        uom: z.string(),
        qty: decimal,
        rate: decimal,
        amount: decimal,
      }),
    ),
    dbt_farmer_payable: decimal,
  })
  .transform((wire) => ({
    pipeSizeMm: wire.pipe_size_mm,
    nozzle: wire.nozzle,
    lines: wire.lines,
    dbtFarmerPayable: wire.dbt_farmer_payable,
  }));

export type SprinklerResult = z.output<typeof sprinklerResultSchema>;

export const calculateResponseSchema = z
  .object({
    data: z.object({
      system_type: systemTypeSchema,
      scheme: z.string(),
      masters: z.object({
        as_of: z.string(),
        formula_version: z.string(),
        regular_matrix_id: z.string(),
        seven_year_matrix_id: z.string(),
        quantity_matrix_id: z.string().nullable(),
      }),
      crops: z.array(cropResultSchema).min(1),
      total: z.object({ blocks: blocksSchema }),
      sprinkler: sprinklerResultSchema.nullable(),
      warnings: z.array(z.string()),
    }),
  })
  .transform(({ data }) => ({
    systemType: data.system_type,
    scheme: data.scheme,
    asOf: data.masters.as_of,
    formulaVersion: data.masters.formula_version,
    crops: data.crops,
    total: data.total.blocks,
    sprinkler: data.sprinkler,
    warnings: data.warnings,
  }));

export type SubsidyCalculation = z.output<typeof calculateResponseSchema>;

/** The wire shapes, for the mock backend. */
export type SubsidyConfigWire = z.input<typeof subsidyConfigSchema>;
export type CalculateResponseWire = z.input<typeof calculateResponseSchema>;
export type BlocksWire = z.input<typeof blocksSchema>;
