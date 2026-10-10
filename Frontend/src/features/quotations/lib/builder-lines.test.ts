import { describe, expect, it } from "vitest";

import type { ProductPick, QuotePreview } from "@/features/quotations/api/quotations.schemas";

import {
  draftLinesFrom,
  lineIssue,
  linesToSave,
  pricedByKey,
  previewRequestFor,
  routeSaveErrors,
  type DraftLine,
} from "./builder-lines";

const PIPE: ProductPick = {
  id: "p-1",
  code: "PL-1001",
  description: "UPVC PIPE 90 MM",
  uom: "MTR",
  uomDecimals: 2,
  hsnCode: "3917",
  gstSlab: "18.00",
  packMultiple: null,
};

function line(key: string, patch: Partial<DraftLine> = {}): DraftLine {
  return { key, product: PIPE, qty: "18", discounts: ["", "", ""], ...patch };
}

const CONTEXT = { placeOfSupplyTerritoryId: "t-1", partnerId: null, asOf: null };

describe("[QUOT-004] lineIssue", () => {
  it("says what a row still needs, and nothing for a finished or an empty row", () => {
    expect(lineIssue(line("a"))).toBeNull();
    expect(lineIssue(line("a", { product: null, qty: "" }))).toBeNull();
    expect(lineIssue(line("a", { product: null }))).toBe("Choose a product");
    expect(lineIssue(line("a", { qty: "0" }))).toBe("Enter a quantity above 0");
    expect(lineIssue(line("a", { qty: "abc" }))).toBe("Enter a quantity above 0");
    expect(lineIssue(line("a", { discounts: ["120", "", ""] }))).toBe(
      "Discounts are percentages from 0 to 100",
    );
    expect(lineIssue(line("a", { discounts: ["2.5555", "", ""] }))).toBe(
      "Discounts are percentages from 0 to 100",
    );
  });
});

describe("[QUOT-005] previewRequestFor", () => {
  it("prices only the finished rows, with empty discounts as 0, in order", () => {
    const plan = previewRequestFor(
      [
        line("a", { discounts: ["10", "5", ""] }),
        line("b", { product: null }),
        line("c", { qty: " 2.5 " }),
      ],
      CONTEXT,
    );

    expect(plan.keys).toEqual(["a", "c"]);
    expect(plan.request).toEqual({
      place_of_supply_territory_id: "t-1",
      lines: [
        {
          product_id: "p-1",
          qty: "18",
          discount_pct: "10",
          discount2_pct: "5",
          discount3_pct: "0",
        },
        {
          product_id: "p-1",
          qty: "2.5",
          discount_pct: "0",
          discount2_pct: "0",
          discount3_pct: "0",
        },
      ],
    });
  });

  it("sends nothing when no row is ready, and the partner and price date when known", () => {
    expect(previewRequestFor([line("a", { product: null, qty: "" })], CONTEXT)).toEqual({
      request: null,
      keys: [],
    });
    expect(
      previewRequestFor([line("a")], { ...CONTEXT, partnerId: "cp-1", asOf: "2026-09-27" }).request,
    ).toMatchObject({ partner_id: "cp-1", as_of: "2026-09-27" });
  });
});

describe("[QUOT-004] pricing and saving", () => {
  const preview: QuotePreview = {
    asOf: "2026-09-27",
    intraState: true,
    totals: {
      gross: "1",
      discount: "0",
      taxable: "1",
      cgst: "0",
      sgst: "0",
      igst: "0",
      total: "1",
    },
    warnings: [],
    lines: [
      {
        lineNo: 1,
        productId: "p-1",
        description: "UPVC PIPE 90 MM",
        hsnCode: "3917",
        uom: "MTR",
        qty: "18.000",
        rate: "103.19",
        gross: "1857.42",
        discounts: [
          { pct: "10.000", amount: "185.74", after: "1671.68" },
          { pct: "5.000", amount: "83.58", after: "1588.10" },
          { pct: "0.000", amount: "0.00", after: "1588.10" },
        ],
        discount: "269.32",
        taxable: "1588.10",
        gstSlab: "5.000",
        cgst: { rate: "2.500", amount: "39.70" },
        sgst: { rate: "2.500", amount: "39.70" },
        igst: { rate: "0.000", amount: "0.00" },
        total: "1667.50",
        priceListItemId: "pli-1",
        gstRateId: "gst-5",
        provisionalFields: [],
      },
    ],
  };

  it("maps each priced line back to its row", () => {
    expect(pricedByKey(preview, ["a"]).get("a")?.total).toBe("1667.50");
    // A preview for a different set of rows is not used.
    expect(pricedByKey(preview, ["a", "b"]).size).toBe(0);
  });

  it("saves what the preview priced, with its price row and tax rate", () => {
    const plan = previewRequestFor([line("a", { discounts: ["10", "5", ""] })], CONTEXT);

    expect(linesToSave(plan, preview)).toEqual([
      {
        product_id: "p-1",
        qty: "18",
        discount_pct: "10",
        discount2_pct: "5",
        discount3_pct: "0",
        price_list_item_id: "pli-1",
        gst_rate_id: "gst-5",
      },
    ]);
  });

  it("turns a saved draft back into rows, without trailing zeros", () => {
    const rows = draftLinesFrom(preview.lines, () => "k");

    expect(rows).toEqual([
      expect.objectContaining({ key: "k", qty: "18", discounts: ["10", "5", "0"] }),
    ]);
    expect(rows[0]?.product?.id).toBe("p-1");
  });
});

describe("[QUOT-004] routeSaveErrors", () => {
  it("puts header fields on the form and line fields on their row, in words", () => {
    expect(
      routeSaveErrors(
        {
          "party.mobile": "not an Indian mobile number",
          "lines[1].qty": "NOS takes whole numbers",
          "lines[0].rate": "now 108.35",
          "lines[0].product_id": "product_inactive: not an active product",
          "lines[9].qty": "no such row",
        },
        ["a", "b"],
      ),
    ).toEqual({
      header: { partyMobile: "Not an Indian mobile number" },
      lines: { a: "Rate: now 108.35", b: "Quantity: nOS takes whole numbers" },
    });
  });
});
