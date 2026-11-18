import { describe, expect, it } from "vitest";

import { toDataSheet } from "@/features/dealer-applications/api/data-sheet.schemas";

import {
  changedDataSheet,
  dataSheetDraftOf,
  dataSheetProblems,
  EMPTY_INSTALLATION,
  EMPTY_WORKING_CAPITAL,
} from "./data-sheet-draft";

const empty = dataSheetDraftOf(toDataSheet({}));

describe("[CHNL-007] The data sheet's checks and changes (FS-071)", () => {
  it("reads a backend before 078 as an empty sheet in square feet", () => {
    expect(toDataSheet({})).toMatchObject({
      workingCapital: [],
      manpower: [],
      previousInstallations: [],
      areaUnit: "sq_ft",
      telephone: null,
    });
  });

  it("checks what the backend checks: dates, lakhs, areas and counts", () => {
    const problems = dataSheetProblems(
      {
        ...empty,
        establishedOn: "2027-01-01",
        otherSourcesLakhs: "123456",
        officeArea: "12.345",
        twoWheelers: "1000",
        installations: [
          { ...EMPTY_INSTALLATION, year: "1949", customers: "2", description: "x", costLakhs: "1" },
        ],
      },
      "2026-11-04",
    );
    expect(problems).toMatchObject({
      established_on: "From 1900, and not after today.",
      other_sources_lakhs: expect.stringContaining("Lakhs"),
      office_area: expect.stringContaining("An area"),
      two_wheelers: "A whole number, up to 999.",
      previous_installations: "Row 1: the year, from 1950 to 2026.",
    });
  });

  it("leaves out a row nobody typed in, rather than refusing it", () => {
    const draft = { ...empty, workingCapital: [EMPTY_WORKING_CAPITAL] };
    expect(dataSheetProblems(draft, "2026-11-04")).toEqual({});
    expect(changedDataSheet(draft, empty)).toEqual({});
  });

  it("sends only what changed, and an emptied table as null", () => {
    const saved = dataSheetDraftOf(
      toDataSheet({ working_capital: [{ facility: "Own funds", amount_lakhs: "5" }], cars: 2 }),
    );
    expect(changedDataSheet({ ...saved, cars: "3" }, saved)).toEqual({ cars: 3 });
    expect(changedDataSheet({ ...saved, workingCapital: [] }, saved)).toEqual({
      working_capital: null,
    });
    expect(changedDataSheet({ ...saved, areaUnit: "sq_m" }, saved)).toEqual({ area_unit: "sq_m" });
  });
});
