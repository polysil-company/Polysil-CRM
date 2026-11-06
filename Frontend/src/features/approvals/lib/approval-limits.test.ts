import { describe, expect, it } from "vitest";

import type { Threshold } from "@/features/approvals/api/approvals.schemas";

import {
  boundsFor,
  boundsHint,
  formatLimit,
  ladderFor,
  mayBeUnlimited,
  outOfBounds,
  overrideTerritories,
} from "./approval-limits";

const RAJKOT = { id: "t-rajkot", name: "Rajkot", level: "district" };

function row(
  docType: Threshold["docType"],
  role: string,
  maxAmount: string | null,
  territory: Threshold["territory"] = null,
): Threshold {
  return { docType, role, territory, maxAmount, unit: docType === "sales_order" ? "inr" : "pct" };
}

const ROWS: Threshold[] = [
  row("sales_order", "district_manager", "100000.00"),
  row("sales_order", "state_manager", "500000.00"),
  row("sales_order", "regional_manager", null),
  row("sales_order", "district_manager", "150000.00", RAJKOT),
  row("quotation", "field_officer", "5.00"),
  row("quotation", "district_manager", "10.00"),
];

describe("[APPR-002] approval limit ladders", () => {
  it("orders each ladder by level, company-wide or a territory's own, with missing rows", () => {
    const orders = ladderFor(ROWS, "sales_order", null);
    expect(orders.map((step) => [step.role, step.row?.maxAmount ?? "none"])).toEqual([
      ["district_manager", "100000.00"],
      ["state_manager", "500000.00"],
      ["regional_manager", "none"],
    ]);
    expect(ladderFor(ROWS, "sales_order", RAJKOT.id)[0]?.row?.maxAmount).toBe("150000.00");
    expect(ladderFor(ROWS, "quotation", null).map((step) => step.row === null)).toEqual([
      false,
      false,
      true,
      true,
      true,
    ]);
    expect(overrideTerritories(ROWS, "sales_order")).toEqual([RAJKOT]);
    expect(overrideTerritories(ROWS, "quotation")).toEqual([]);
  });

  it("keeps each level between its neighbours, and says so in words", () => {
    const orders = ladderFor(ROWS, "sales_order", null);
    const state = boundsFor(orders, "state_manager");
    expect(state).toEqual({ above: 100000, under: null });
    expect(boundsFor(orders, "district_manager")).toEqual({ above: null, under: 500000 });
    expect(outOfBounds(90000, state, "inr")).toBe("Must be above ₹1,00,000, the level below");
    expect(outOfBounds(600000, boundsFor(orders, "district_manager"), "inr")).toBe(
      "Must be under ₹5,00,000, the level above",
    );
    expect(outOfBounds(200000, state, "inr")).toBeNull();
    expect(boundsHint(state, "inr")).toBe(
      "Above ₹1,00,000, to keep each level above the one below.",
    );
    expect(boundsHint({ above: null, under: null }, "pct")).toBeNull();
  });

  it("lets only the top of a ladder go without a limit", () => {
    expect(mayBeUnlimited("sales_order", "regional_manager")).toBe(true);
    expect(mayBeUnlimited("sales_order", "state_manager")).toBe(false);
    expect(mayBeUnlimited("quotation", "admin_sales")).toBe(true);
    expect(mayBeUnlimited("quotation", "regional_manager")).toBe(false);
    expect(formatLimit("100000.00", "inr")).toBe("Up to ₹1,00,000");
    expect(formatLimit("12.50", "pct")).toBe("Up to 12.5%");
    expect(formatLimit(null, "pct")).toBe("No limit");
  });
});
