import { describe, expect, it } from "vitest";

import { dispatchFormSchemaFor, type DispatchForm } from "./orders.schemas";

const NOW = Date.parse("2026-09-29T10:00:00.000Z");
const schema = dispatchFormSchemaFor(
  [
    { id: "pipe", qtyOpen: "8.000", uomDecimals: 0 },
    { id: "lateral", qtyOpen: "120.500", uomDecimals: 1 },
  ],
  () => NOW,
);

function form(overrides: Partial<DispatchForm> = {}): DispatchForm {
  return {
    dispatchedAt: "2026-09-29T09:00:00.000Z",
    dcNo: "",
    dcDate: "",
    invoiceNo: "",
    invoiceDate: "",
    transporter: "",
    vehicleNo: "",
    lines: [
      { orderLineId: "pipe", qty: "" },
      { orderLineId: "lateral", qty: "" },
    ],
    ...overrides,
  };
}

function messages(value: DispatchForm): Record<string, string> {
  const result = schema.safeParse(value);
  return Object.fromEntries(
    (result.error?.issues ?? []).map((issue) => [issue.path.join("."), issue.message]),
  );
}

describe("[DISP-002] dispatchFormSchemaFor", () => {
  it("needs at least one item, and a time not in the future", () => {
    expect(messages(form())).toEqual({ lines: "Enter what left for at least one item" });
    expect(
      messages(
        form({
          dispatchedAt: "2026-09-29T12:00:00.000Z",
          lines: [{ orderLineId: "pipe", qty: "1" }],
        }),
      ),
    ).toEqual({ dispatchedAt: "It can't be in the future" });
  });

  it("checks each quantity against what is open, in the unit's precision", () => {
    expect(
      messages(
        form({
          lines: [
            { orderLineId: "pipe", qty: "2.5" },
            { orderLineId: "lateral", qty: "121" },
          ],
        }),
      ),
    ).toEqual({ "lines.0.qty": "Whole units only", "lines.1.qty": "More than is still open" });
    expect(messages(form({ lines: [{ orderLineId: "lateral", qty: "12.25" }] }))).toEqual({
      "lines.0.qty": "At most 1 decimals",
    });
    expect(messages(form({ lines: [{ orderLineId: "lateral", qty: "abc" }] }))).toEqual({
      "lines.0.qty": "A number, like 12 or 2.5",
    });
    expect(
      schema.safeParse(
        form({
          lines: [
            { orderLineId: "pipe", qty: "8" },
            { orderLineId: "lateral", qty: "" },
          ],
        }),
      ).success,
    ).toBe(true);
  });
});
