import { SYSTEM_TYPES, type SystemType } from "@/features/subsidy/api/subsidy.schemas";
import { MOCK_SPRINKLER_COMPONENTS, MOCK_SUBSIDY_PARAMETERS } from "@/mocks/data/subsidy";
import { emptySubsidyMasters, type MockSubsidyMasters } from "@/mocks/data/subsidy-masters";
import { MOCK_DEFAULT_SCHEME, type MockScheme } from "@/mocks/data/subsidy-schemes";
import { mockDb } from "@/mocks/db";

import { errorResponse } from "./shared";

/**
 * SUBS-014 · What a calculation on a scheme's system would refuse on, in the engine's order
 * (`readiness` in the backend's subsidy service): the unit-cost matrices, categories, crop
 * spacings, the quantity matrix and its rows, the parameters, then the component rates the
 * quantities ask for. The mock's required parameters and rows are GGRC's.
 */

function inForce(
  row: { effective_from: string; effective_to: string | null },
  on: string,
): boolean {
  return row.effective_from <= on && (row.effective_to === null || row.effective_to > on);
}

export function mockScheme(code: string | null | undefined): MockScheme | undefined {
  const wanted = (code ?? MOCK_DEFAULT_SCHEME).toUpperCase();
  return mockDb.subsidySchemes.find((scheme) => scheme.code === wanted);
}

export function mockMasters(code: string): MockSubsidyMasters {
  return mockDb.subsidyMasters.get(code) ?? emptySubsidyMasters();
}

/** The parameters a system reads, as the seed names them: `key` or `<system>.key`. */
function requiredParameters(system: SystemType): string[] {
  return Object.keys(MOCK_SUBSIDY_PARAMETERS).flatMap((name) => {
    const [first, second] = name.split(".");
    if (second === undefined) return [name];
    return first === system ? [second] : [];
  });
}

export function missingFor(code: string, system: SystemType, on: string): string[] {
  const masters = mockMasters(code);
  const missing: string[] = [];
  const dimensionality = system === "sprinkler" ? 1 : 2;
  for (const variant of ["regular", "seven_year"] as const) {
    const matrix = masters.unitCostMatrices.find(
      (row) => row.system_type === system && row.variant === variant && inForce(row, on),
    );
    if (matrix === undefined || matrix.dimensionality !== dimensionality) {
      missing.push(`unit_cost_matrix:${variant}`);
    }
  }
  if (!masters.categories.some((row) => row.system_type === system && inForce(row, on))) {
    missing.push("categories");
  }
  if (!masters["crop-spacings"].some((row) => inForce(row, on))) missing.push("crop_spacings");
  let quantities = false;
  if (system === "sprinkler") {
    const matrix = masters.quantityMatrices.find(
      (row) => row.system_type === system && inForce(row, on),
    );
    if (matrix === undefined) missing.push("quantity_matrix");
    else {
      quantities = true;
      for (const item of MOCK_SPRINKLER_COMPONENTS) {
        if (!matrix.cells.some((cell) => cell.component_code === item.component)) {
          missing.push(`quantity_matrix:${item.component}`);
        }
      }
    }
  }
  const parameters = masters.parameters.filter(
    (row) => (row.system_type === null || row.system_type === system) && inForce(row, on),
  );
  for (const key of requiredParameters(system)) {
    if (!parameters.some((row) => row.key === key)) missing.push(`parameters:${key}`);
  }
  if (quantities) {
    const rates = masters["component-rates"].filter(
      (row) => row.system_type === system && inForce(row, on),
    );
    const wanted = [
      ...MOCK_SPRINKLER_COMPONENTS.flatMap((item) =>
        (["75", "90"] as const).map((size) => ({ code: item.component, size, nozzle: null })),
      ),
      ...(["plastic", "brass"] as const).map((nozzle) => ({ code: "nozzle", size: null, nozzle })),
    ];
    for (const { code: component, size, nozzle } of wanted) {
      const found = rates.some(
        (row) =>
          row.component_code === component &&
          (size === null || String(row.pipe_size_mm) === size) &&
          (nozzle === null || row.nozzle === nozzle),
      );
      if (!found) missing.push(`component_rate:${component}:${size ?? nozzle}`);
    }
  }
  return missing;
}

export function schemeReady(scheme: MockScheme, on: string): boolean {
  return (
    scheme.stages.some((stage) => stage.is_active) &&
    scheme.systems.every((system) => missingFor(scheme.code, system, on).length === 0)
  );
}

/** The systems a scheme runs, in the order the screens list them. */
export function systemsOf(scheme: MockScheme): SystemType[] {
  return SYSTEM_TYPES.filter((system) => scheme.systems.includes(system));
}

/** `?scheme=` on the calculator's endpoints: an active scheme, or the backend's 422. */
export function readActiveScheme(code: string | null | undefined): MockScheme | Response {
  const scheme = mockScheme(code);
  if (scheme === undefined || !scheme.is_active) {
    return errorResponse(422, "validation_error", "Some fields need correcting.", {
      scheme: `'${(code ?? MOCK_DEFAULT_SCHEME).toUpperCase()}' is not an active scheme.`,
    });
  }
  return scheme;
}
