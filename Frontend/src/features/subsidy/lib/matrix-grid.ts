import type {
  QuantityCell,
  QuantityMatrix,
  UnitCostCell,
  UnitCostMatrix,
} from "@/features/subsidy/api/subsidy-masters.schemas";

/**
 * SUBS-013 · Matrices as grids the administrator copies from, and pastes back from, Excel:
 * tab-separated rows, the first row the area breakpoints, the first column the lateral spacing
 * (unit costs) or the component (quantities). A new matrix carries every cell, so the grid is
 * read whole; any cell that doesn't read is named by its row and column.
 */

export interface ParsedGrid<TCell> {
  readonly cells: TCell[];
  readonly problems: string[];
}

const CORNER_UNIT_COST = "Spacing \\ Area";
const CORNER_QUANTITY = "Component \\ Area";

/** Excel copies "1,12,000" with grouping; the backend wants "112000". */
function clean(value: string): string {
  return value.trim().replace(/,/g, "");
}

function decimalProblem(value: string, places: number): string | null {
  if (!/^\d+(\.\d+)?$/.test(value)) return "isn't a number";
  if ((value.split(".")[1]?.length ?? 0) > places) {
    return `has more than ${String(places)} decimals`;
  }
  return null;
}

function rowsOf(text: string): string[][] {
  return text
    .split(/\r?\n/)
    .map((line) => line.split("\t"))
    .filter((cells) => cells.some((cell) => cell.trim() !== ""));
}

function uniqueSorted(values: readonly string[]): string[] {
  return [...new Set(values)].sort((a, b) => Number(a) - Number(b));
}

/** The header row's areas, each checked; problems are added to the list given. */
function readAreas(header: readonly string[], problems: string[]): string[] {
  const areas = header.slice(1).map(clean);
  if (areas.length === 0)
    problems.push("The first row needs the area breakpoints after its first cell.");
  areas.forEach((area, index) => {
    const problem = decimalProblem(area, 3);
    if (problem !== null) problems.push(`Area ${String(index + 1)} ("${area}") ${problem}.`);
  });
  if (new Set(areas).size !== areas.length) problems.push("An area breakpoint appears twice.");
  return areas;
}

export function unitCostGridOf(matrix: UnitCostMatrix): string {
  const areas = uniqueSorted(matrix.cells.map((cell) => cell.area_breakpoint));
  const spacings = [...new Set(matrix.cells.map((cell) => cell.lateral_spacing))];
  const lines = [[CORNER_UNIT_COST, ...areas].join("\t")];
  for (const spacing of spacings) {
    const values = areas.map(
      (area) =>
        matrix.cells.find(
          (cell) => cell.lateral_spacing === spacing && cell.area_breakpoint === area,
        )?.unit_cost ?? "",
    );
    lines.push([spacing ?? "Unit cost", ...values].join("\t"));
  }
  return lines.join("\n");
}

/**
 * A pasted unit-cost grid. Two-dimensional: one row per lateral spacing. One-dimensional:
 * a single row of unit costs by area, its first cell a label.
 */
export function parseUnitCostGrid(text: string, dimensionality: 1 | 2): ParsedGrid<UnitCostCell> {
  const problems: string[] = [];
  const [header, ...body] = rowsOf(text);
  if (header === undefined) return { cells: [], problems: ["Paste the grid first."] };
  const areas = readAreas(header, problems);
  if (body.length === 0) problems.push("Add at least one row of unit costs under the areas.");
  if (dimensionality === 1 && body.length > 1) {
    problems.push("A one-dimensional matrix has a single row of unit costs.");
  }
  const cells: UnitCostCell[] = [];
  const spacings = new Set<string>();
  body.forEach((row, rowIndex) => {
    const label = clean(row[0] ?? "");
    const at = `Row ${String(rowIndex + 2)}`;
    let spacing: string | null = null;
    if (dimensionality === 2) {
      const problem = decimalProblem(label, 2);
      if (problem !== null) problems.push(`${at}: the spacing ("${label}") ${problem}.`);
      else if (spacings.has(label)) problems.push(`${at}: the spacing ${label} appears twice.`);
      spacing = label;
      spacings.add(label);
    }
    const values = row.slice(1).map(clean);
    if (values.length !== areas.length) {
      problems.push(`${at} has ${String(values.length)} values for ${String(areas.length)} areas.`);
    }
    areas.forEach((area, column) => {
      const value = values[column] ?? "";
      const problem = decimalProblem(value, 4);
      if (problem !== null) {
        problems.push(`${at}, area ${area}: "${value}" ${problem}.`);
        return;
      }
      cells.push({ lateral_spacing: spacing, area_breakpoint: area, unit_cost: value });
    });
  });
  return { cells: problems.length > 0 ? [] : cells, problems };
}

export function quantityGridOf(matrix: QuantityMatrix): string {
  const areas = uniqueSorted(matrix.cells.map((cell) => cell.area_breakpoint));
  const components = [...new Set(matrix.cells.map((cell) => cell.component_code))];
  const lines = [[CORNER_QUANTITY, ...areas].join("\t")];
  for (const component of components) {
    const values = areas.map(
      (area) =>
        matrix.cells.find(
          (cell) => cell.component_code === component && cell.area_breakpoint === area,
        )?.qty ?? "",
    );
    lines.push([component, ...values].join("\t"));
  }
  return lines.join("\n");
}

/** A pasted quantity grid: one row per component, its code first. */
export function parseQuantityGrid(text: string): ParsedGrid<QuantityCell> {
  const problems: string[] = [];
  const [header, ...body] = rowsOf(text);
  if (header === undefined) return { cells: [], problems: ["Paste the grid first."] };
  const areas = readAreas(header, problems);
  if (body.length === 0) problems.push("Add at least one component row under the areas.");
  const cells: QuantityCell[] = [];
  const components = new Set<string>();
  body.forEach((row, rowIndex) => {
    const component = (row[0] ?? "").trim();
    const at = `Row ${String(rowIndex + 2)}`;
    if (component === "") problems.push(`${at} needs its component code first.`);
    else if (components.has(component)) problems.push(`${at}: ${component} appears twice.`);
    components.add(component);
    const values = row.slice(1).map(clean);
    if (values.length !== areas.length) {
      problems.push(`${at} has ${String(values.length)} values for ${String(areas.length)} areas.`);
    }
    areas.forEach((area, column) => {
      const value = values[column] ?? "";
      const problem = decimalProblem(value, 2);
      if (problem !== null) {
        problems.push(`${at}, area ${area}: "${value}" ${problem}.`);
        return;
      }
      cells.push({ component_code: component, area_breakpoint: area, qty: value });
    });
  });
  return { cells: problems.length > 0 ? [] : cells, problems };
}
