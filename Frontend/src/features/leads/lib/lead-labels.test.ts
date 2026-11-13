import { describe, expect, it } from "vitest";

import type { Lead } from "@/features/leads/api/leads.schemas";

import { describeCreatedLead, formatScore, landText } from "./lead-labels";

type Duplicate = Lead["duplicates"][number];

function duplicate(code: string, state: Duplicate["state"] = "pending"): Duplicate {
  return { linkId: `l-${code}`, leadId: `id-${code}`, code, signal: "mobile", score: null, state };
}

function lead(duplicates: Duplicate[]): Pick<Lead, "customerName" | "code" | "duplicates"> {
  return { customerName: "Ramesh Patel", code: "POL/GJ/2026-27/00123", duplicates };
}

describe("[LEAD-002] describeCreatedLead", () => {
  it("names the new lead, and counts every possible duplicate as the lead page does", () => {
    expect(describeCreatedLead(lead([]))).toBe("Ramesh Patel · POL/GJ/2026-27/00123");
    expect(describeCreatedLead(lead([duplicate("A"), duplicate("B", "dismissed")]))).toBe(
      "Ramesh Patel · POL/GJ/2026-27/00123. Possible duplicate of A (same mobile number), flagged for review.",
    );
    expect(describeCreatedLead(lead([duplicate("A"), duplicate("B"), duplicate("C")]))).toBe(
      "Ramesh Patel · POL/GJ/2026-27/00123. 3 possible duplicates (A, B and C), flagged for review.",
    );
  });
});

describe("[LEAD-003] formatScore", () => {
  it("shows the score as the whole number the backend now sends (walk 10 Oct)", () => {
    expect(formatScore("28.00")).toBe("28");
    expect(formatScore("100.00")).toBe("100");
  });
});

describe("[LEAD-003] landText", () => {
  it("says the land in hectares, with acres beside them (FS-052)", () => {
    expect(landText({ landHectares: "1.82", landAcres: "4.50" })).toBe("1.82 hectares (4.5 acres)");
    expect(landText({ landHectares: "2.00", landAcres: null })).toBe("2 hectares");
    expect(landText({ landHectares: null, landAcres: "4.50" })).toBe("4.5 acres");
    expect(landText({ landHectares: null, landAcres: null })).toBe("—");
  });
});
