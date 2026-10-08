import { describe, expect, it } from "vitest";

import type { SystemConfig } from "@/features/subsidy/api/subsidy.schemas";

import {
  emptyDraft,
  emptyLine,
  linePaths,
  planCalculation,
  readWarning,
  type CalculatorDraft,
} from "./calculator-draft";
import { ratioAsPercent, warningTitle } from "./subsidy-labels";

const DRIP: SystemConfig = {
  systemType: "drip",
  hasHeadUnit: true,
  supportsGroup: true,
  cropCountMax: 2,
  formulaVersion: "v1",
  sprinklerAreas: null,
};

const SPRINKLER: SystemConfig = {
  systemType: "sprinkler",
  hasHeadUnit: false,
  supportsGroup: false,
  cropCountMax: 1,
  formulaVersion: "v1",
  sprinklerAreas: ["0.400", "2.010"],
};

function dripDraft(patch: Partial<CalculatorDraft> = {}): CalculatorDraft {
  const draft = emptyDraft("drip");
  const crop = draft.crops[0];
  if (crop === undefined) throw new Error("emptyDraft has one crop");
  return {
    ...draft,
    crops: [{ ...crop, crop: "Mango", area: "1.5", lateralSpacing: "5" }],
    ...patch,
  };
}

describe("[SUBS-002] planCalculation", () => {
  it("sends nothing until each crop has its area and spacing, and calls that missing", () => {
    const plan = planCalculation(emptyDraft("drip"), DRIP);
    expect(plan.request).toBeNull();
    expect(plan.missing).toEqual(["crops[0].area", "crops[0].lateral_spacing"]);
    expect(plan.problems).toEqual({});
  });

  it("builds the request as typed, leaving out blank rows and empty extras", () => {
    const plan = planCalculation(dripDraft(), DRIP);
    expect(plan.request).toEqual({
      system_type: "drip",
      crops: [
        {
          crop: "Mango",
          inter_crop: null,
          area: "1.5",
          crop_spacing: "",
          lateral_spacing: "5",
          lines: [],
        },
      ],
      head_lines: [],
    });
  });

  it("marks a half-typed row and too many decimals by the backend's paths", () => {
    const base = dripDraft();
    const crop = base.crops[0];
    if (crop === undefined) throw new Error("one crop");
    const plan = planCalculation(
      {
        ...base,
        crops: [
          {
            ...crop,
            area: "1.2345",
            lines: [emptyLine(), { ...emptyLine(), description: "Lateral", rate: "1.234" }],
          },
        ],
        groupTotalArea: "0",
      },
      DRIP,
    );
    expect(plan.request).toBeNull();
    expect(plan.problems).toMatchObject({
      "crops[0].area": "Use at most 3 decimals.",
      "crops[0].lines[0].uom": expect.any(String),
      "crops[0].lines[0].rate": "Use at most 2 decimals.",
      "crops[0].lines[0].qty": expect.any(String),
      group_total_area: "The group's area must be more than 0.",
    });
  });

  it("sends Sprinkler only its nozzle and a tabulated area — no lines, head unit or group", () => {
    const draft = emptyDraft("sprinkler");
    const crop = draft.crops[0];
    if (crop === undefined) throw new Error("one crop");
    const off = planCalculation(
      { ...draft, crops: [{ ...crop, area: "1.300", lateralSpacing: "12" }] },
      SPRINKLER,
    );
    expect(off.problems["crops[0].area"]).toBe("Choose one of the scheme's areas.");

    const plan = planCalculation(
      {
        ...draft,
        crops: [{ ...crop, area: "2.010", lateralSpacing: "12" }],
        groupTotalArea: "5",
        sumpRate: "100",
        nozzle: "brass",
      },
      SPRINKLER,
    );
    expect(plan.request).toEqual({
      system_type: "sprinkler",
      crops: [
        {
          crop: null,
          inter_crop: null,
          area: "2.010",
          crop_spacing: "",
          lateral_spacing: "12",
          lines: [],
        },
      ],
      nozzle: "brass",
    });
  });

  it("numbers a row's path among the filled rows", () => {
    const blank = emptyLine();
    const filled = { ...emptyLine(), description: "Filter" };
    expect(linePaths([blank, filled], "head_lines")).toEqual({ [filled.key]: "head_lines[0]" });
  });
});

describe("[SUBS-002] warnings and labels", () => {
  it("splits a warning on the first colon and reads the seven-year prefix", () => {
    expect(readWarning("area_below_table: Below 0.4 Ha: clamped.")).toEqual({
      code: "area_below_table",
      sentence: "Below 0.4 Ha: clamped.",
    });
    expect(readWarning("No code here")).toEqual({ code: "", sentence: "No code here" });
    expect(warningTitle("seven_year_area_below_table")).toBe(
      "Area below the scheme's table (seven-year)",
    );
    expect(warningTitle("something_new")).toBeNull();
  });

  it("prints a ratio from the masters as a percentage", () => {
    expect(ratioAsPercent("0.0028")).toBe("0.28%");
    expect(ratioAsPercent("0.025")).toBe("2.5%");
    expect(ratioAsPercent("0.09")).toBe("9%");
    expect(ratioAsPercent("0.1")).toBe("10%");
    expect(ratioAsPercent(undefined)).toBeNull();
  });
});
