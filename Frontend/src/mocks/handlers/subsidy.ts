import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  systemTypeSchema,
  type BlockKey,
  type BlocksWire,
  type CalculateResponseWire,
  type SubsidyConfigWire,
  type SystemType,
} from "@/features/subsidy/api/subsidy.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import {
  MOCK_FORMULA_VERSION,
  MOCK_SPRINKLER_AREAS,
  MOCK_SPRINKLER_COMPONENTS,
  MOCK_SPRINKLER_NOZZLE_RATE,
  MOCK_SUBSIDY_AS_OF,
  MOCK_SUBSIDY_CATEGORIES,
  MOCK_SUBSIDY_CROPS,
  MOCK_SUBSIDY_PARAMETERS,
} from "@/mocks/data/subsidy";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * SUBS-002, SUBS-003 · The subsidy calculation and its lookups. The mock's arithmetic is a
 * plausible stand-in with the same shape — blocks, unit cost, eight categories, warnings — and
 * the backend's refusals; the real figures come only from the backend's engine.
 */

const SEVEN_YEAR_MIN = 0.2;
const SEVEN_YEAR_MAX = 5;
const SEVEN_YEAR_SPACING_FLOOR = 1.2;
const MAX_TABLE_SPACING = 10;

function mayView(): boolean {
  return mockPermissionsFor(readMockRole()).some(
    (permission) => permission.module === "subsidy" && permission.actions.includes("view"),
  );
}

const SYSTEMS: readonly {
  systemType: SystemType;
  hasHeadUnit: boolean;
  supportsGroup: boolean;
  cropCountMax: number;
}[] = [
  { systemType: "drip", hasHeadUnit: true, supportsGroup: true, cropCountMax: 2 },
  { systemType: "mini_sprinkler", hasHeadUnit: true, supportsGroup: true, cropCountMax: 1 },
  { systemType: "sprinkler", hasHeadUnit: false, supportsGroup: false, cropCountMax: 1 },
];

/** Unit cost per hectare at a lateral spacing, before the area scales it. */
const BASE_RATE: Readonly<Record<SystemType, number>> = {
  drip: 160_000,
  mini_sprinkler: 120_000,
  sprinkler: 30_000,
};

const decimal = (places: number): z.ZodType<string> =>
  z
    .string()
    .regex(/^\d+(\.\d+)?$/)
    .refine((value) => (value.split(".")[1]?.length ?? 0) <= places, {
      message: `at most ${String(places)} decimals`,
    });

const lineSchema = z.object({
  description: z.string().trim().min(1).max(300),
  uom: z.string().trim().min(1).max(20),
  rate: decimal(2),
  qty: decimal(3),
});

const requestSchema = z.object({
  system_type: systemTypeSchema,
  crops: z
    .array(
      z.object({
        crop: z.string().nullable(),
        inter_crop: z.string().nullable(),
        area: decimal(3),
        crop_spacing: z.string().max(60),
        lateral_spacing: decimal(2),
        lines: z.array(lineSchema).max(200),
      }),
    )
    .min(1),
  head_lines: z.array(lineSchema).max(200).optional(),
  sump: z.object({ rate_per_ha: decimal(2) }).optional(),
  group_total_area: decimal(3).optional(),
  installation_rate_per_ha: decimal(2).optional(),
  nozzle: z.enum(["plastic", "brass"]).optional(),
});

export type CalculateBody = z.infer<typeof requestSchema>;

const money = (value: number): string => value.toFixed(2);
const sumLines = (lines: readonly { rate: string; qty: string }[]): number =>
  lines.reduce((total, line) => total + Number(line.rate) * Number(line.qty), 0);

function standardSpacing(name: string | null): number {
  if (name === null) return 0;
  const key = name.trim().toLowerCase();
  return MOCK_SUBSIDY_CROPS.find((row) => row.crop.toLowerCase() === key)?.standardSpacing ?? 0;
}

function knownCrop(name: string | null): boolean {
  if (name === null) return true;
  const key = name.trim().toLowerCase();
  return MOCK_SUBSIDY_CROPS.some((row) => row.crop.toLowerCase() === key);
}

/** The refusals the backend makes, each naming its field. */
function refusals(body: CalculateBody): Record<string, string> {
  const fields: Record<string, string> = {};
  const system = SYSTEMS.find((row) => row.systemType === body.system_type);
  if (system !== undefined && body.crops.length > system.cropCountMax) {
    fields.crops = `${body.system_type} takes at most ${String(system.cropCountMax)} crop block(s)`;
  }
  body.crops.forEach((crop, index) => {
    const at = `crops[${String(index)}]`;
    if (!knownCrop(crop.crop)) fields[`${at}.crop`] = "not in the crop table";
    if (!knownCrop(crop.inter_crop)) fields[`${at}.inter_crop`] = "not in the crop table";
    if (Number(crop.area) <= 0) fields[`${at}.area`] = "must be more than 0";
    if (Number(crop.lateral_spacing) <= 0) fields[`${at}.lateral_spacing`] = "must be more than 0";
    if (body.system_type === "sprinkler") {
      if (!MOCK_SPRINKLER_AREAS.some((area) => Number(area) === Number(crop.area))) {
        fields[`${at}.area`] =
          "Sprinkler areas are the scheme's steps: 0.4 to 5.0 Ha in steps of 0.2, or 2.01 Ha";
      }
      if (crop.lines.length > 0) fields[`${at}.lines`] = "Sprinkler derives its own lines";
    }
  });
  const totalArea = body.crops.reduce((total, crop) => total + Number(crop.area), 0);
  if (body.group_total_area !== undefined && Number(body.group_total_area) < totalArea - 1e-9) {
    fields.group_total_area = "must be at least the sum of the crop areas";
  }
  if (body.system_type === "sprinkler" && body.nozzle === undefined) {
    fields.nozzle = "choose plastic or brass";
  }
  return fields;
}

interface Costs {
  head: number;
  field: number;
  area: number;
  areaShare: number;
  installationRate: number;
  sumpRate: number;
  inspectionFloor: number;
}

function blocksFor(costs: Costs): { blocks: BlocksWire; totalInclGst: number } {
  const gstMaterial = 0.025;
  const gstService = 0.09;
  const aPlusB = costs.head + costs.field;
  const gstAb = aPlusB * gstMaterial;
  const installation = costs.installationRate * costs.area;
  const gstC = installation * gstService;
  const totalAbc = aPlusB + 2 * gstAb + installation + 2 * gstC;
  const insurance = totalAbc * 0.0028;
  const gstD = insurance * gstService;
  const inspection = Math.max(totalAbc * 0.004, costs.inspectionFloor * costs.areaShare);
  const gstE = inspection * gstService;
  const education = 1000 * costs.areaShare;
  const sump = costs.sumpRate * costs.area;
  const costExcl = aPlusB + installation + insurance + inspection + education + sump;
  const halfGst = gstAb + gstC + gstD + gstE;
  const totalInclGst = costExcl + 2 * halfGst;
  return {
    totalInclGst,
    blocks: {
      head_unit: money(costs.head),
      field_unit: money(costs.field),
      a_plus_b: money(aPlusB),
      cgst_ab: money(gstAb),
      sgst_ab: money(gstAb),
      installation: money(installation),
      cgst_c: money(gstC),
      sgst_c: money(gstC),
      total_abc_gst: money(totalAbc),
      insurance: money(insurance),
      cgst_d: money(gstD),
      sgst_d: money(gstD),
      inspection: money(inspection),
      cgst_e: money(gstE),
      sgst_e: money(gstE),
      education: money(education),
      sump: money(sump),
      cost_excl_gst: money(costExcl),
      total_cgst: money(halfGst),
      total_sgst: money(halfGst),
      total_gst: money(2 * halfGst),
      total_incl_gst: money(totalInclGst),
    },
  };
}

function sumBlocks(columns: readonly BlocksWire[]): BlocksWire {
  const total = (key: BlockKey): string =>
    money(columns.reduce((sum, column) => sum + Number(column[key]), 0));
  return {
    head_unit: total("head_unit"),
    field_unit: total("field_unit"),
    a_plus_b: total("a_plus_b"),
    cgst_ab: total("cgst_ab"),
    sgst_ab: total("sgst_ab"),
    installation: total("installation"),
    cgst_c: total("cgst_c"),
    sgst_c: total("sgst_c"),
    total_abc_gst: total("total_abc_gst"),
    insurance: total("insurance"),
    cgst_d: total("cgst_d"),
    sgst_d: total("sgst_d"),
    inspection: total("inspection"),
    cgst_e: total("cgst_e"),
    sgst_e: total("sgst_e"),
    education: total("education"),
    sump: total("sump"),
    cost_excl_gst: total("cost_excl_gst"),
    total_cgst: total("total_cgst"),
    total_sgst: total("total_sgst"),
    total_gst: total("total_gst"),
    total_incl_gst: total("total_incl_gst"),
  };
}

function sprinklerLines(
  area: number,
  nozzle: "plastic" | "brass",
): NonNullable<CalculateResponseWire["data"]["sprinkler"]> {
  const pipe: 75 | 90 = area <= 2 ? 75 : 90;
  const rows = MOCK_SPRINKLER_COMPONENTS.map((item) => {
    const qty = Math.ceil(item.perHa * area);
    return {
      component: item.component,
      description: item.description.replace("pipe", `pipe ${String(pipe)} mm`),
      uom: item.uom,
      qty: qty.toFixed(3),
      rate: money(item.rate[pipe]),
      amount: money(qty * item.rate[pipe]),
    };
  });
  const nozzles = Math.ceil(10 * area);
  rows.push({
    component: "nozzle",
    description: `Sprinkler nozzle, 5 to 40 litre/minute (${nozzle})`,
    uom: "No.",
    qty: nozzles.toFixed(3),
    rate: money(MOCK_SPRINKLER_NOZZLE_RATE[nozzle]),
    amount: money(nozzles * MOCK_SPRINKLER_NOZZLE_RATE[nozzle]),
  });
  rows.push({
    component: "transport",
    description: "Secondary transportation",
    uom: "Set",
    qty: "1.000",
    rate: "506.45",
    amount: "506.45",
  });
  const field = rows.reduce((total, row) => total + Number(row.amount), 0);
  return {
    pipe_size_mm: pipe,
    nozzle,
    lines: rows,
    dbt_farmer_payable: money(field * 1.05),
  };
}

export function calculate(body: CalculateBody): CalculateResponseWire["data"] {
  const system = body.system_type;
  const totalArea = body.crops.reduce((total, crop) => total + Number(crop.area), 0);
  const groupArea = body.group_total_area === undefined ? totalArea : Number(body.group_total_area);
  const head = sumLines(body.head_lines ?? []);
  const sumpRate = Number(body.sump?.rate_per_ha ?? "0");
  const installationRate = Number(body.installation_rate_per_ha ?? "0");
  const inspectionFloor = Number(MOCK_SUBSIDY_PARAMETERS[`${system}.inspection_floor`] ?? "0");
  const sprinkler =
    system === "sprinkler" && body.nozzle !== undefined
      ? sprinklerLines(Number(body.crops[0]?.area ?? "0"), body.nozzle)
      : null;
  const responseWarnings: string[] = [];
  if (sumpRate > 0) {
    responseWarnings.push(
      "sump_ignored_by_workbook: The sump is counted here; the scheme's spreadsheet leaves it out.",
    );
  }

  const crops = body.crops.map((crop) => {
    const area = Number(crop.area);
    const designed = Number(crop.lateral_spacing);
    // The inter-crop, when there is one, sets the standard spacing.
    const standard = standardSpacing(crop.inter_crop ?? crop.crop);
    const forSubsidy = Math.max(designed, standard);
    const warnings: string[] = [];
    if (forSubsidy > MAX_TABLE_SPACING) {
      warnings.push(
        `spacing_outside_table: ${forSubsidy.toFixed(2)} m is beyond the table; the figure uses the ${MAX_TABLE_SPACING.toFixed(2)} m row.`,
      );
    }
    if (area < 0.4) {
      warnings.push("area_below_table: The area is below the smallest the table holds (0.4 Ha).");
    }
    if (area > 5) {
      warnings.push("area_above_table: The area is above 5 Ha; the unit cost is scaled.");
    }
    const sevenYearApplies =
      area >= SEVEN_YEAR_MIN && area <= SEVEN_YEAR_MAX && forSubsidy >= SEVEN_YEAR_SPACING_FLOOR;
    if (!sevenYearApplies) {
      warnings.push(
        "seven_year_not_applicable: The seven-year rows apply from 0.2 to 5 Ha, at 1.20 m or wider.",
      );
    }

    const field =
      system === "sprinkler"
        ? (sprinkler?.lines ?? []).reduce((total, row) => total + Number(row.amount), 0)
        : sumLines(crop.lines);
    const areaShare = groupArea > 0 ? area / groupArea : 0;
    const { blocks, totalInclGst } = blocksFor({
      head: head * areaShare,
      field,
      area,
      areaShare,
      installationRate,
      sumpRate,
      inspectionFloor,
    });

    const perHa = BASE_RATE[system] * Math.pow(1.2 / Math.min(forSubsidy, MAX_TABLE_SPACING), 0.55);
    const regular = perHa * Math.min(area, 5) * (area > 5 ? area / 5 : 1);
    const withSump = regular + sumpRate * area;
    // A Mini Sprinkler block below 0.2 Ha is pro-rated.
    const forCap = system === "mini_sprinkler" && area < 0.2 ? withSump * (area / 0.2) : withSump;
    const sevenYear = sevenYearApplies ? forCap * 2.4 : null;

    const categories = MOCK_SUBSIDY_CATEGORIES[system].map((category) => {
      const applicable = category.variant === "regular" || sevenYear !== null;
      const cap = category.variant === "regular" ? forCap : (sevenYear ?? 0);
      const subsidy = applicable
        ? Math.min((totalInclGst * category.pct) / 100, (cap * category.pct) / 100)
        : 0;
      const farmerShare = applicable ? totalInclGst - subsidy : 0;
      const gsdma =
        category.gsdmaPct !== null && totalArea <= 2 && applicable
          ? money(Math.max(0, farmerShare - (totalInclGst * category.gsdmaPct) / 100))
          : null;
      return {
        code: category.code,
        name: category.name,
        pct: String(category.pct),
        variant: category.variant,
        applicable,
        reason: applicable
          ? null
          : "The seven-year rows apply from 0.2 to 5 Ha, at 1.20 m spacing or wider.",
        subsidy: money(subsidy),
        farmer_share: money(farmerShare),
        subsidy_pct: money(totalInclGst > 0 ? (subsidy / totalInclGst) * 100 : 0),
        gsdma_farmer_share: gsdma,
      };
    });

    return {
      crop: crop.crop,
      inter_crop: crop.inter_crop,
      area: area.toFixed(3),
      lateral_spacing_designed: designed.toFixed(2),
      lateral_spacing_standard: standard.toFixed(2),
      lateral_spacing_for_subsidy: forSubsidy.toFixed(2),
      blocks,
      jantri: {
        regular: regular.toFixed(4),
        regular_with_sump: withSump.toFixed(4),
        regular_for_cap: forCap.toFixed(4),
        seven_year: sevenYear === null ? null : sevenYear.toFixed(4),
      },
      categories,
      warnings,
    };
  });

  return {
    system_type: system,
    scheme: "GGRC",
    masters: {
      as_of: MOCK_SUBSIDY_AS_OF,
      formula_version: MOCK_FORMULA_VERSION,
      regular_matrix_id: "mock-regular",
      seven_year_matrix_id: "mock-seven-year",
      quantity_matrix_id: system === "sprinkler" ? "mock-quantity" : null,
    },
    crops,
    total: { blocks: sumBlocks(crops.map((crop) => crop.blocks)) },
    sprinkler,
    warnings: responseWarnings,
  };
}

/** The request read and checked as the backend does: each refusal names its field path. */
export function checkCalculation(
  json: unknown,
): { readonly body: CalculateBody } | { readonly fields: Record<string, string> } {
  const parsed = requestSchema.safeParse(json);
  if (!parsed.success) {
    const fields: Record<string, string> = {};
    for (const issue of parsed.error.issues) {
      const path = issue.path
        .map((part, index) =>
          typeof part === "number"
            ? `[${String(part)}]`
            : `${index === 0 ? "" : "."}${String(part)}`,
        )
        .join("");
      fields[path] = issue.message;
    }
    return { fields };
  }
  const fields = refusals(parsed.data);
  return Object.keys(fields).length > 0 ? { fields } : { body: parsed.data };
}

export const subsidyHandlers = [
  http.get(buildApiUrl("/subsidy/config"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "You may not see subsidy.");
    const data: SubsidyConfigWire["data"] = {
      scheme: "GGRC",
      as_of: MOCK_SUBSIDY_AS_OF,
      systems: SYSTEMS.map((system) => ({
        system_type: system.systemType,
        has_head_unit: system.hasHeadUnit,
        supports_group: system.supportsGroup,
        crop_count_max: system.cropCountMax,
        spacing_rule: "max_of_designed_and_standard",
        seven_year_spacing_floor: SEVEN_YEAR_SPACING_FLOOR.toFixed(2),
        quantity_source: system.systemType === "sprinkler" ? "matrix" : "design",
        formula_version: MOCK_FORMULA_VERSION,
        sprinkler_areas: system.systemType === "sprinkler" ? [...MOCK_SPRINKLER_AREAS] : null,
      })),
      parameters: { ...MOCK_SUBSIDY_PARAMETERS },
    };
    return HttpResponse.json({ data });
  }),

  http.get(buildApiUrl("/subsidy/crops"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "You may not see subsidy.");
    return HttpResponse.json({
      data: MOCK_SUBSIDY_CROPS.map((row) => ({
        crop: row.crop,
        standard_spacing: row.standardSpacing.toFixed(2),
      })),
    });
  }),

  http.get(buildApiUrl("/subsidy/categories"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "You may not see subsidy.");
    const system = systemTypeSchema.safeParse(new URL(request.url).searchParams.get("system_type"));
    if (!system.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        system_type: "drip, mini_sprinkler or sprinkler",
      });
    }
    return HttpResponse.json({
      data: MOCK_SUBSIDY_CATEGORIES[system.data].map((row) => ({
        code: row.code,
        name: row.name,
        pct: String(row.pct),
        variant: row.variant,
        gsdma_pct: row.gsdmaPct === null ? null : String(row.gsdmaPct),
      })),
    });
  }),

  http.post(buildApiUrl("/subsidy/calculate"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayView()) return errorResponse(403, "forbidden", "You may not see subsidy.");
    const checked = checkCalculation(await request.json());
    if ("fields" in checked) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", checked.fields);
    }
    return HttpResponse.json({ data: calculate(checked.body) });
  }),
];
