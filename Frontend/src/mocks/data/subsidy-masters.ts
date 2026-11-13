import type {
  CategoryRow,
  ComponentRateRow,
  CropSpacingRow,
  ParameterRow,
  QuantityMatrix,
  UnitCostMatrix,
} from "@/features/subsidy/api/subsidy-masters.schemas";
import { SYSTEM_TYPES, type SystemType } from "@/features/subsidy/api/subsidy.schemas";

import { MOCK_ID_SPACE, mockUuid } from "./reference";
import {
  MOCK_SPRINKLER_COMPONENTS,
  MOCK_SPRINKLER_NOZZLE_RATE,
  MOCK_SUBSIDY_AS_OF,
  MOCK_SUBSIDY_CATEGORIES,
  MOCK_SUBSIDY_CROPS,
  MOCK_SUBSIDY_PARAMETERS,
} from "./subsidy";

/**
 * SUBS-012, SUBS-013 · The mock's subsidy masters as the admin screens read them, built from the
 * same figures the mock's calculator uses. All start on the mock's masters date and have no end.
 * The calculator mock doesn't re-read them after a revision; the backend's engine does.
 */

export interface MockSubsidyMasters {
  categories: CategoryRow[];
  parameters: ParameterRow[];
  "component-rates": ComponentRateRow[];
  "crop-spacings": CropSpacingRow[];
  unitCostMatrices: UnitCostMatrix[];
  quantityMatrices: QuantityMatrix[];
}

let serial = 0;
function nextId(): string {
  serial += 1;
  return mockUuid(MOCK_ID_SPACE.subsidyMaster, serial);
}

const WINDOW = { effective_from: MOCK_SUBSIDY_AS_OF, effective_to: null } as const;

const PARAMETER_UNITS: Readonly<Record<string, string>> = {
  education_amount: "rupees",
  insurance_rate: "ratio",
  inspection_rate: "ratio",
  gst_material_half: "ratio",
  gst_service_half: "ratio",
  seven_year_area_min: "hectares",
  seven_year_area_max: "hectares",
  inspection_floor: "rupees",
};

const SPACINGS = ["0.60", "1.20", "2.50", "5.00"] as const;
const AREAS = ["0.400", "1.000", "2.000", "5.000"] as const;
const BASE_RATE: Readonly<Record<SystemType, number>> = {
  drip: 160_000,
  mini_sprinkler: 120_000,
  sprinkler: 30_000,
};

function unitCost(system: SystemType, seven: boolean, spacing: number, area: number): string {
  const perHa = BASE_RATE[system] * Math.pow(1.2 / spacing, 0.55) * (seven ? 2.4 : 1);
  return (perHa * area).toFixed(4);
}

/** A new scheme's masters: nothing until an administrator enters its own figures (SUBS-014). */
export function emptySubsidyMasters(): MockSubsidyMasters {
  return {
    categories: [],
    parameters: [],
    "component-rates": [],
    "crop-spacings": [],
    unitCostMatrices: [],
    quantityMatrices: [],
  };
}

export function seedSubsidyMasters(): MockSubsidyMasters {
  serial = 0;
  const categories: CategoryRow[] = SYSTEM_TYPES.flatMap((system) =>
    MOCK_SUBSIDY_CATEGORIES[system].map((row, index) => ({
      id: nextId(),
      ...WINDOW,
      system_type: system,
      code: row.code,
      name: row.name,
      pct: String(row.pct),
      variant: row.variant,
      per_ha_cap: null,
      gsdma_pct: row.gsdmaPct === null ? null : String(row.gsdmaPct),
      sort_order: index,
    })),
  );

  const parameters: ParameterRow[] = Object.entries(MOCK_SUBSIDY_PARAMETERS).map(
    ([name, value]) => {
      const [first, second] = name.split(".");
      const system = SYSTEM_TYPES.find((item) => item === first) ?? null;
      const key = system === null ? name : (second ?? name);
      return {
        id: nextId(),
        ...WINDOW,
        system_type: system,
        key,
        value,
        unit: PARAMETER_UNITS[key] ?? "ratio",
      };
    },
  );

  const componentRates: ComponentRateRow[] = [
    ...MOCK_SPRINKLER_COMPONENTS.flatMap((item) =>
      ([75, 90] as const).map((pipe) => ({
        id: nextId(),
        ...WINDOW,
        system_type: "sprinkler" as const,
        component_code: item.component,
        description: item.description,
        uom: item.uom,
        pipe_size_mm: pipe,
        nozzle: null,
        rate: item.rate[pipe].toFixed(2),
        source_cell: "BOQ",
      })),
    ),
    ...(["plastic", "brass"] as const).map((nozzle) => ({
      id: nextId(),
      ...WINDOW,
      system_type: "sprinkler" as const,
      component_code: "nozzle",
      description: `Sprinkler nozzle, 5 to 40 litre/minute (${nozzle})`,
      uom: "No.",
      pipe_size_mm: null,
      nozzle,
      rate: MOCK_SPRINKLER_NOZZLE_RATE[nozzle].toFixed(2),
      source_cell: "Farmer Share Calculation",
    })),
  ];

  const cropSpacings: CropSpacingRow[] = MOCK_SUBSIDY_CROPS.map((row, index) => ({
    id: nextId(),
    ...WINDOW,
    crop: row.crop,
    standard_spacing: row.standardSpacing.toFixed(2),
    sort_order: index,
  }));

  const unitCostMatrices: UnitCostMatrix[] = SYSTEM_TYPES.flatMap((system) =>
    (["regular", "seven_year"] as const).map((variant) => {
      const twoD = system !== "sprinkler";
      const spacings: readonly (string | null)[] = twoD ? SPACINGS : [null];
      return {
        id: nextId(),
        ...WINDOW,
        system_type: system,
        variant,
        dimensionality: twoD ? (2 as const) : (1 as const),
        source: "GGRC unit cost table, 2026",
        cells: spacings.flatMap((spacing) =>
          AREAS.map((area) => ({
            lateral_spacing: spacing,
            area_breakpoint: area,
            unit_cost: unitCost(
              system,
              variant === "seven_year",
              spacing === null ? 1.2 : Number(spacing),
              Number(area),
            ),
          })),
        ),
      };
    }),
  );

  const quantityMatrices: QuantityMatrix[] = [
    {
      id: nextId(),
      ...WINDOW,
      system_type: "sprinkler",
      source: "GGRC sprinkler quantities, 2026",
      cells: MOCK_SPRINKLER_COMPONENTS.flatMap((item) =>
        AREAS.map((area) => ({
          component_code: item.component,
          area_breakpoint: area,
          qty: Math.ceil(item.perHa * Number(area)).toFixed(2),
        })),
      ),
    },
  ];

  return {
    categories,
    parameters,
    "component-rates": componentRates,
    "crop-spacings": cropSpacings,
    unitCostMatrices,
    quantityMatrices,
  };
}
