import type { SystemType } from "@/features/subsidy/api/subsidy.schemas";

/**
 * SUBS-002, SUBS-003 · The mock's subsidy masters. The crops, categories and constants follow
 * the shape of the scheme's tables (backend migration `009_subsidy_masters`); the spacings and
 * rates are made up for the mock and are not the client's figures.
 */

export const MOCK_SUBSIDY_AS_OF = "2026-06-13";
export const MOCK_FORMULA_VERSION = "ggrc-2026-06-13";

/** Crop name → standard lateral spacing in metres. */
export const MOCK_SUBSIDY_CROPS: readonly { crop: string; standardSpacing: number }[] = [
  { crop: "Banana", standardSpacing: 1.8 },
  { crop: "Castor", standardSpacing: 1.5 },
  { crop: "Chikoo", standardSpacing: 5 },
  { crop: "Cotton", standardSpacing: 1.2 },
  { crop: "Groundnut", standardSpacing: 0.9 },
  { crop: "Lemon", standardSpacing: 4 },
  { crop: "Mango", standardSpacing: 5 },
  { crop: "Papaya", standardSpacing: 1.8 },
  { crop: "Pomegranate", standardSpacing: 4.5 },
  { crop: "Sugarcane", standardSpacing: 1.8 },
  { crop: "Vegetables", standardSpacing: 1 },
  { crop: "Wheat", standardSpacing: 0.6 },
];

export interface MockSubsidyCategory {
  readonly code: string;
  readonly name: string;
  readonly pct: number;
  readonly variant: "regular" | "seven_year";
  readonly gsdmaPct: number | null;
}

function categories(
  names: readonly [string, string, string, string, string, string, string, string],
  gsdma: readonly [number, number] | null,
): readonly MockSubsidyCategory[] {
  const rows: readonly [string, number, "regular" | "seven_year", number | null][] = [
    ["small_farmer", 70, "regular", gsdma?.[0] ?? null],
    ["darkzone_small_farmer", 80, "regular", gsdma?.[0] ?? null],
    ["big_farmer", 70, "regular", gsdma?.[0] ?? null],
    ["darkzone_big_farmer", 70, "regular", gsdma?.[0] ?? null],
    ["sc_st", 85, "regular", gsdma?.[1] ?? null],
    ["darkzone_sc_st", 90, "regular", gsdma?.[1] ?? null],
    ["seven_year_small", 55, "seven_year", null],
    ["seven_year_big", 45, "seven_year", null],
  ];
  return rows.map(([code, pct, variant, gsdmaPct], index) => ({
    code,
    name: names[index] ?? code,
    pct,
    variant,
    gsdmaPct,
  }));
}

export const MOCK_SUBSIDY_CATEGORIES: Readonly<Record<SystemType, readonly MockSubsidyCategory[]>> =
  {
    drip: categories(
      [
        "Small Farmer 70 %",
        "Darkzone Small Farmer 80%",
        "Big Farmer 70 %",
        "Darkzone Big Farmer 70 %",
        "SC+ST 85 %",
        "Darkzone + SC/ST 90%",
        "7 Year Small farmer",
        "7 Year Big Farmer",
      ],
      null,
    ),
    mini_sprinkler: categories(
      [
        "Small Farmer 70 %",
        "Darkzone Small Farmer 80%",
        "Big Farmer 70 %",
        "Darkzone Big Farmer 70 %",
        "SC+ST 85 %",
        "Darkzone + SC/ST 90%",
        "7 Year Small farmer 55 %",
        "7 Year Big Farmer 45%",
      ],
      [10, 5],
    ),
    sprinkler: categories(
      [
        "Small Farmer 70%",
        "Small Farmer+Darkzone 80%",
        "General Farmer 70%",
        "General Farmer+Darkzone 70%",
        "SC+ST (TRIBAL) Farmer 85 %",
        "SC+ST (TRIBAL)+Dark Zone Farmer 90 %",
        "Small Farmer 55%",
        "Big Farmer 45%",
      ],
      null,
    ),
  };

/** 0.4 to 5.0 in steps of 0.2, plus 2.01 — the areas the Sprinkler table holds. */
export const MOCK_SPRINKLER_AREAS: readonly string[] = [
  ...Array.from({ length: 24 }, (_, index) => ((index + 2) * 0.2).toFixed(3)),
  "2.010",
].sort((a, b) => Number(a) - Number(b));

export const MOCK_SUBSIDY_PARAMETERS: Readonly<Record<string, string>> = {
  education_amount: "1000",
  insurance_rate: "0.0028",
  inspection_rate: "0.004",
  gst_material_half: "0.025",
  gst_service_half: "0.09",
  seven_year_area_min: "0.2",
  seven_year_area_max: "5",
  "drip.inspection_floor": "0",
  "mini_sprinkler.inspection_floor": "200",
  "sprinkler.inspection_floor": "200",
};

/** The rows the Sprinkler BOQ derives from the area. Rates are made up for the mock. */
export const MOCK_SPRINKLER_COMPONENTS: readonly {
  component: string;
  description: string;
  uom: string;
  rate: Readonly<Record<75 | 90, number>>;
  /** Units per hectare. */
  perHa: number;
}[] = [
  {
    component: "pipe",
    description: "HDPE sprinkler pipe with SS C clamp coupler",
    uom: "Mtr.",
    rate: { 75: 583.12, 90: 691.62 },
    perHa: 75,
  },
  {
    component: "coupler",
    description: "Sprinkler coupler with foot batten, quick action",
    uom: "No.",
    rate: { 75: 391.49, 90: 410.23 },
    perHa: 12.5,
  },
  {
    component: "riser",
    description: "Riser pipe 20 mm × 75 cm",
    uom: "No.",
    rate: { 75: 90.15, 90: 90.15 },
    perHa: 10,
  },
  {
    component: "pcn",
    description: "Sprinkler PCN (nipple) with SS C clamp",
    uom: "No.",
    rate: { 75: 269.04, 90: 334 },
    perHa: 2.5,
  },
  {
    component: "bend",
    description: "Sprinkler bend with SS C clamp",
    uom: "No.",
    rate: { 75: 282.63, 90: 294.71 },
    perHa: 2.5,
  },
  {
    component: "end_plug",
    description: "Sprinkler end plug",
    uom: "No.",
    rate: { 75: 110.97, 90: 127.18 },
    perHa: 2.5,
  },
];

export const MOCK_SPRINKLER_NOZZLE_RATE: Readonly<Record<"plastic" | "brass", number>> = {
  plastic: 104.17,
  brass: 299.23,
};
