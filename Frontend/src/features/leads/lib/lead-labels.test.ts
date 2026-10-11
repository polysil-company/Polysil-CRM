import { describe, expect, it } from "vitest";

import type { Lead } from "@/features/leads/api/leads.schemas";

import { describeCreatedLead } from "./lead-labels";

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
