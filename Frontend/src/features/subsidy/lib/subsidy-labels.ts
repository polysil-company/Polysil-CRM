import type { BlockKey, SystemType } from "@/features/subsidy/api/subsidy.schemas";
import { formatNumber } from "@/lib/format";

/** SUBS-002 · Words for the calculator's codes. */

export const SYSTEM_LABELS: Readonly<Record<SystemType, string>> = {
  drip: "Drip",
  mini_sprinkler: "Mini Sprinkler",
  sprinkler: "Sprinkler",
};

/** How a row of the summary reads: a lettered block, its GST, or a total. */
export type BlockTone = "block" | "tax" | "subtotal" | "total";

export interface BlockRow {
  readonly key: BlockKey;
  readonly label: string;
  readonly tone: BlockTone;
  /** The `GET /subsidy/config` parameter whose rate the label prints, e.g. insurance. */
  readonly rate?: string;
}

/** The quotation summary, top to bottom, as the scheme's sheet prints it. */
export const BLOCK_ROWS: readonly BlockRow[] = [
  { key: "head_unit", label: "A · Head unit", tone: "block" },
  { key: "field_unit", label: "B · Field unit", tone: "block" },
  { key: "a_plus_b", label: "A + B", tone: "subtotal" },
  { key: "cgst_ab", label: "CGST on A + B", tone: "tax", rate: "gst_material_half" },
  { key: "sgst_ab", label: "SGST on A + B", tone: "tax", rate: "gst_material_half" },
  { key: "installation", label: "C · Installation", tone: "block" },
  { key: "cgst_c", label: "CGST on C", tone: "tax", rate: "gst_service_half" },
  { key: "sgst_c", label: "SGST on C", tone: "tax", rate: "gst_service_half" },
  { key: "total_abc_gst", label: "A + B + C with GST", tone: "subtotal" },
  { key: "insurance", label: "D · Insurance", tone: "block", rate: "insurance_rate" },
  { key: "cgst_d", label: "CGST on D", tone: "tax", rate: "gst_service_half" },
  { key: "sgst_d", label: "SGST on D", tone: "tax", rate: "gst_service_half" },
  {
    key: "inspection",
    label: "E · Third-party inspection",
    tone: "block",
    rate: "inspection_rate",
  },
  { key: "cgst_e", label: "CGST on E", tone: "tax", rate: "gst_service_half" },
  { key: "sgst_e", label: "SGST on E", tone: "tax", rate: "gst_service_half" },
  { key: "education", label: "Farmer education", tone: "block" },
  { key: "sump", label: "Sump", tone: "block" },
  { key: "cost_excl_gst", label: "Cost without GST", tone: "subtotal" },
  { key: "total_cgst", label: "Total CGST", tone: "tax" },
  { key: "total_sgst", label: "Total SGST", tone: "tax" },
  { key: "total_gst", label: "Total GST", tone: "subtotal" },
  { key: "total_incl_gst", label: "Total with GST", tone: "total" },
];

/**
 * A ratio from the masters as a percentage to print: "0.0028" → "0.28%". Display only — the
 * figures beside it come from the backend. Null when the parameter is missing or unreadable.
 */
export function ratioAsPercent(ratio: string | undefined): string | null {
  if (ratio === undefined || !/^\d+(\.\d+)?$/.test(ratio)) return null;
  const percent = Number(ratio) * 100;
  if (Number.isInteger(percent)) return `${formatNumber(percent)}%`;
  // "2.50" → "2.5"; only a fraction's trailing zeros go.
  return `${formatNumber(percent, 2).replace(/\.?0+$/, "")}%`;
}

/** The titles of the warnings the engine sends; an unknown code shows its sentence alone. */
const WARNING_TITLES: Readonly<Record<string, string>> = {
  spacing_outside_table: "Spacing outside the scheme's table",
  area_below_table: "Area below the scheme's table",
  area_above_table: "Area above 5 Ha",
  seven_year_not_applicable: "Seven-year rows don't apply",
  rounding_residual: "A paisa of rounding",
  sump_ignored_by_workbook: "Sump counted here, not in the scheme's sheet",
};

/**
 * "seven_year_area_below_table" is the seven-year table's clamp, a different figure from the
 * regular one, so the prefix is read rather than matched away.
 */
export function warningTitle(code: string): string | null {
  const direct = WARNING_TITLES[code];
  if (direct !== undefined) return direct;
  if (code.startsWith("seven_year_")) {
    const base = WARNING_TITLES[code.slice("seven_year_".length)];
    if (base !== undefined) return `${base} (seven-year)`;
  }
  return null;
}
