import { describe, expect, it } from "vitest";

import {
  formatQuantity,
  formatRate,
  parseWarnings,
  quotationNumber,
  quotationTitle,
} from "./quotation-labels";

describe("[QUOT-002] quotation labels", () => {
  it("prints rates without trailing zeros, keeping whole numbers whole", () => {
    expect(formatRate("10.000")).toBe("10%");
    expect(formatRate("2.500")).toBe("2.5%");
    expect(formatRate("0.000")).toBe("0%");
    expect(formatRate("18.000")).toBe("18%");
    expect(formatRate("not a rate")).toBe("—");
  });

  it("prints quantities the same way", () => {
    expect(formatQuantity("18.000")).toBe("18");
    expect(formatQuantity("2.500")).toBe("2.5");
    expect(formatQuantity("1250.000")).toBe("1,250");
  });

  it("names a draft 'Draft' and shows the version only once there is more than one", () => {
    expect(quotationNumber({ quoteNo: null })).toBe("Draft");
    expect(quotationTitle({ quoteNo: "QT/GJ/2026-27/00001", version: 1 })).toBe(
      "QT/GJ/2026-27/00001",
    );
    expect(quotationTitle({ quoteNo: "QT/GJ/2026-27/00001", version: 2 })).toBe(
      "QT/GJ/2026-27/00001 · v2",
    );
  });

  it("splits each warning on its first colon into a code and a sentence", () => {
    expect(
      parseWarnings([
        "provisional_pricing: 1 of 3 lines use stand-in rates",
        "repriced: line 2: rate 103.19 -> 108.35",
        "no code here",
      ]),
    ).toEqual([
      { code: "provisional_pricing", message: "1 of 3 lines use stand-in rates" },
      { code: "repriced", message: "Line 2: rate 103.19 -> 108.35" },
      { code: "", message: "no code here" },
    ]);
  });
});
