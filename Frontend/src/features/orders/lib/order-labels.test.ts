import { describe, expect, it } from "vitest";

import { warehouseShortText } from "./order-labels";

describe("[APP-009] A short warehouse on an order line (live test N-04)", () => {
  it("says what is missing when stock is over-committed, never a negative amount", () => {
    expect(warehouseShortText("-500.000", "MTR", 0)).toBe("Warehouse short by 500 MTR");
    expect(warehouseShortText("-12.5", "KG", 1)).toBe("Warehouse short by 12.5 KG");
  });

  it("says how little is left when some stock remains", () => {
    expect(warehouseShortText("40", "NOS", 0)).toBe("Warehouse short: only 40 NOS available");
    expect(warehouseShortText("0", "MTR", 0)).toBe("Warehouse short: only 0 MTR available");
  });
});
