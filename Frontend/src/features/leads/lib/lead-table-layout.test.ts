import { describe, expect, it } from "vitest";

import { LEAD_COLUMN_LAYOUT, LEAD_COLUMN_META } from "./lead-table-layout";

describe("[LEAD-001] leads table layout", () => {
  it("shares leftover width across several columns, so a wide monitor leaves no single gap", () => {
    const flexible = LEAD_COLUMN_LAYOUT.filter((meta) => meta.width === "fill");

    expect(flexible.length).toBeGreaterThan(1);
  });

  it("gives every other column a width, so only the text columns stretch", () => {
    const sized = LEAD_COLUMN_LAYOUT.filter((meta) => meta.width !== undefined);

    expect(sized).toHaveLength(LEAD_COLUMN_LAYOUT.length);
    expect(LEAD_COLUMN_META.customerName.isRowHeader).toBe(true);
  });
});
