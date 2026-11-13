import { describe, expect, it } from "vitest";

import type {
  QuantityMatrix,
  UnitCostMatrix,
} from "@/features/subsidy/api/subsidy-masters.schemas";

import {
  changedRowIds,
  editProblem,
  effectiveFromProblem,
  sentValue,
  type EditableField,
} from "./master-revision";
import {
  parseQuantityGrid,
  parseUnitCostGrid,
  quantityGridOf,
  unitCostGridOf,
} from "./matrix-grid";
import { readMissing } from "./scheme-readiness";

const PCT: EditableField = { key: "pct", label: "Subsidy %", places: 3, required: true, max: 100 };
const CAP: EditableField = { key: "per_ha_cap", label: "Cap", places: 2, required: false };

describe("[SUBS-012] master revision", () => {
  it("checks a figure as typed", () => {
    expect(editProblem(PCT, "")).toBe("Enter the subsidy %.");
    expect(editProblem(PCT, "abc")).toBe("Enter a number, like 12.50.");
    expect(editProblem(PCT, "12.3456")).toBe("At most 3 decimals.");
    expect(editProblem(PCT, "101")).toBe("At most 100.");
    expect(editProblem(PCT, "75.5")).toBeNull();
    expect(editProblem(CAP, "")).toBeNull();
  });

  it("checks a choice and a whole number", () => {
    const system: EditableField = {
      key: "system_type",
      label: "System",
      required: true,
      options: [{ value: "drip", label: "Drip" }],
    };
    expect(editProblem(system, "")).toBe("Choose the system.");
    expect(editProblem(system, "rain")).toBe("Choose one of the list.");
    const pipe: EditableField = { key: "pipe", label: "Pipe", required: false, integer: true };
    expect(editProblem(pipe, "7.5")).toBe("Enter a whole number.");
    expect(editProblem(pipe, "75")).toBeNull();
  });

  it("sends only rows whose figures changed, with an emptied optional figure as null", () => {
    const rows = [
      { id: "a", pct: "50", per_ha_cap: null },
      { id: "b", pct: "40", per_ha_cap: "1000.00" },
    ];
    expect(changedRowIds(rows, [PCT, CAP], { a: { pct: " 50 " }, b: { per_ha_cap: "" } })).toEqual([
      "b",
    ]);
    expect(sentValue(CAP, " ")).toBeNull();
    expect(sentValue(PCT, " 60 ")).toBe("60");
  });

  it("starts a revision today or later", () => {
    expect(effectiveFromProblem("", "2026-10-09")).toBe("Choose the date it starts.");
    expect(effectiveFromProblem("2026-10-08", "2026-10-09")).toMatch(/^Today or later/);
    expect(effectiveFromProblem("2026-10-09", "2026-10-09")).toBeNull();
  });
});

describe("[SUBS-013] matrix grids", () => {
  const unitCost: UnitCostMatrix = {
    id: "m",
    effective_from: "2026-04-01",
    effective_to: null,
    system_type: "drip",
    variant: "regular",
    dimensionality: 2,
    source: null,
    cells: [
      { lateral_spacing: "1.20", area_breakpoint: "1.000", unit_cost: "100.0000" },
      { lateral_spacing: "1.20", area_breakpoint: "0.400", unit_cost: "40.0000" },
      { lateral_spacing: "2.50", area_breakpoint: "0.400", unit_cost: "30.0000" },
      { lateral_spacing: "2.50", area_breakpoint: "1.000", unit_cost: "80.0000" },
    ],
  };

  it("copies a unit-cost matrix as a grid and reads it back", () => {
    const grid = unitCostGridOf(unitCost);
    expect(grid.split("\n")[0]).toBe("Spacing \\ Area\t0.400\t1.000");
    const parsed = parseUnitCostGrid(grid, 2);
    expect(parsed.problems).toEqual([]);
    expect(parsed.cells).toHaveLength(4);
  });

  it("reads Excel's grouped numbers and names each bad cell", () => {
    const ok = parseUnitCostGrid("x\t0.4\t1\nUnit cost\t1,12,000\t2,00,000", 1);
    expect(ok.cells.map((cell) => cell.unit_cost)).toEqual(["112000", "200000"]);
    expect(ok.cells[0]?.lateral_spacing).toBeNull();
    const bad = parseUnitCostGrid("x\t0.4\t1\n1.2\tabc", 2);
    expect(bad.cells).toEqual([]);
    expect(bad.problems).toEqual([
      "Row 2 has 1 values for 2 areas.",
      'Row 2, area 0.4: "abc" isn\'t a number.',
      'Row 2, area 1: "" isn\'t a number.',
    ]);
    expect(parseUnitCostGrid("", 2).problems).toEqual(["Paste the grid first."]);
    expect(parseUnitCostGrid("x\t1\na\t1\nb\t2", 1).problems).toContain(
      "A one-dimensional matrix has a single row of unit costs.",
    );
  });

  it("copies and reads a quantity grid, refusing a repeated component", () => {
    const quantity: QuantityMatrix = {
      id: "q",
      effective_from: "2026-04-01",
      effective_to: null,
      system_type: "sprinkler",
      source: null,
      cells: [
        { component_code: "hdpe_pipe", area_breakpoint: "0.400", qty: "10.00" },
        { component_code: "hdpe_pipe", area_breakpoint: "1.000", qty: "25.00" },
      ],
    };
    const parsed = parseQuantityGrid(quantityGridOf(quantity));
    expect(parsed.problems).toEqual([]);
    expect(parsed.cells).toEqual(quantity.cells);
    expect(parseQuantityGrid("x\t1\npipe\t1\npipe\t2").problems).toEqual([
      "Row 3: pipe appears twice.",
    ]);
  });
});

describe("[SUBS-014] readiness items", () => {
  it("says each missing item in words, with the table that fills it", () => {
    expect(readMissing("unit_cost_matrix:seven_year")).toEqual({
      text: "The seven-year unit-cost matrix",
      table: "unit-costs",
    });
    expect(readMissing("quantity_matrix")).toEqual({
      text: "The quantity matrix",
      table: "quantities",
    });
    expect(readMissing("quantity_matrix:riser").text).toBe("The quantity matrix's riser row");
    expect(readMissing("categories").table).toBe("categories");
    expect(readMissing("crop_spacings").table).toBe("crop-spacings");
    expect(readMissing("parameters:insurance_rate")).toEqual({
      text: "The insurance_rate parameter",
      table: "parameters",
    });
    expect(readMissing("component_rate:nozzle:brass")).toEqual({
      text: "The nozzle brass rate",
      table: "component-rates",
    });
    expect(readMissing("stages")).toEqual({
      text: "No active stage: contact support",
      table: null,
    });
    expect(readMissing("something_new")).toEqual({ text: "something_new", table: null });
  });
});
