import { describe, expect, it } from "vitest";

import type { ProductPick, QuotePreview } from "@/features/quotations/api/quotations.schemas";

import {
  draftFreightFrom,
  draftLinesFrom,
  freightIssue,
  freightToSave,
  lineIssue,
  linesToSave,
  pricedByKey,
  draftLinesFromImport,
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
  return { key, product: PIPE, qty: "18", discounts: ["", "", ""], gstSlab: null, ...patch };
}

const CONTEXT = { placeOfSupplyTerritoryId: "t-1", partnerId: null, asOf: null, salesType: null };

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
      freight: "0",
      taxable: "1",
      cgst: "0",
      sgst: "0",
      igst: "0",
      total: "1",
    },
    warnings: [],
    freight: null,
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
        hsnSlab: "5.000",
        gstSlabChosen: false,
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
    // QUOT-015 · a line that follows its HSN carries no picked slab
    expect(rows[0]?.gstSlab).toBeNull();
  });

  it("[QUOT-015] keeps a saved line's picked slab, and its HSN slab on the product", () => {
    const [first] = preview.lines;
    if (first === undefined) throw new Error("No line");
    const rows = draftLinesFrom(
      [{ ...first, gstSlab: "40.000", hsnSlab: "5.000", gstSlabChosen: true }],
      () => "k",
    );
    expect(rows[0]?.gstSlab).toBe("40");
    expect(rows[0]?.product?.gstSlab).toBe("5.000");
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
      freight: null,
    });
  });
});

describe("[MSTR-008] the sale type on the price preview", () => {
  it("sends the document's sale type, so the preview prices from that type's list first", () => {
    expect(
      previewRequestFor([line("a")], { ...CONTEXT, salesType: "subsidised" }).request,
    ).toMatchObject({ sales_type: "subsidised" });
    expect(previewRequestFor([line("a")], CONTEXT).request).not.toHaveProperty("sales_type");
  });
});

describe("[MSTR-007] draftLinesFromImport", () => {
  it("turns an import's good rows into builder rows, the unit left to the preview", () => {
    let next = 0;
    const rows = draftLinesFromImport(
      [
        {
          row: 2,
          productId: "p-1",
          product: "INLINE DRIPPER 4 LPH",
          qty: "120.000",
          discounts: ["5.00", "0", "0"],
        },
      ],
      () => {
        next += 1;
        return `k-${String(next)}`;
      },
    );

    expect(rows).toEqual([
      {
        key: "k-1",
        product: {
          id: "p-1",
          code: null,
          description: "INLINE DRIPPER 4 LPH",
          uom: "",
          uomDecimals: 3,
          hsnCode: null,
          gstSlab: null,
          packMultiple: null,
        },
        qty: "120",
        discounts: ["5", "0", "0"],
        gstSlab: null,
      },
    ]);
  });
});

describe("[QUOT-015] a GST slab per line, and freight", () => {
  const COMMERCIAL = { ...CONTEXT, salesType: "commercial" };

  it("sends a slab only for a line where one was picked, and only where the sale takes it", () => {
    const request = previewRequestFor([line("a"), line("b", { gstSlab: "5" })], COMMERCIAL).request;
    expect(request?.lines[0]).not.toHaveProperty("gst_slab");
    expect(request?.lines[1]).toMatchObject({ gst_slab: "5" });

    for (const salesType of ["subsidised", "export", null]) {
      const other = previewRequestFor([line("b", { gstSlab: "5" })], { ...CONTEXT, salesType });
      expect(other.request?.lines[0]).not.toHaveProperty("gst_slab");
    }
    // An industrial export under a LUT is not taxed at home.
    expect(
      previewRequestFor([line("b", { gstSlab: "5" })], {
        ...CONTEXT,
        salesType: "industrial",
        taxTreatment: "export_lut",
      }).request?.lines[0],
    ).not.toHaveProperty("gst_slab");
  });

  it("sends freight once it reads as rupees, with its slab only when picked", () => {
    const freight = (amount: string, gstSlab: string | null = null) =>
      previewRequestFor([line("a")], COMMERCIAL, { amount, gstSlab });
    expect(freight("").request).not.toHaveProperty("freight");
    expect(freight("12.345").request).not.toHaveProperty("freight");
    expect(freight("1500").request?.freight).toEqual({ amount: "1500" });
    expect(freight(" 1500.5 ", "18").request?.freight).toEqual({
      amount: "1500.5",
      gst_slab: "18",
    });
    expect(freightToSave(freight("1500"))).toEqual({ amount: "1500" });
    expect(freightToSave(freight(""))).toBeNull();
    expect(
      previewRequestFor(
        [line("a")],
        { ...CONTEXT, salesType: "subsidised" },
        {
          amount: "1500",
          gstSlab: null,
        },
      ).request,
    ).not.toHaveProperty("freight");
  });

  it("says what's wrong with a freight amount", () => {
    expect(freightIssue({ amount: "", gstSlab: null })).toBeNull();
    expect(freightIssue({ amount: "99999999.99", gstSlab: null })).toBeNull();
    for (const amount of ["0", "-5", "abc", "1.234", "100000000"]) {
      expect(freightIssue({ amount, gstSlab: null })).toBe(
        "Rupees above 0, with at most two decimals",
      );
    }
  });

  it("puts a refused slab on its line and a refused freight on the freight", () => {
    expect(
      routeSaveErrors(
        {
          "lines[0].gst_slab": "28 % is not one of the GST slabs offered.",
          "freight.amount": "Rupees above 0, with at most two decimals.",
        },
        ["a"],
      ),
    ).toEqual({
      header: {},
      lines: { a: "GST: 28 % is not one of the GST slabs offered." },
      freight: "Rupees above 0, with at most two decimals.",
    });
    expect(
      routeSaveErrors({ "freight.gst_slab": "12 % is not one of the GST slabs offered." }, [])
        .freight,
    ).toBe("GST: 12 % is not one of the GST slabs offered.");
  });

  it("restores a draft's freight, keeping a default slab as the default", () => {
    const freight = {
      amount: "2000.00",
      gstSlab: "18.000",
      gstSlabChosen: false,
      cgst: { rate: "9.000", amount: "180.00" },
      sgst: { rate: "9.000", amount: "180.00" },
      igst: { rate: "0.000", amount: "0.00" },
      total: "2360.00",
    };
    expect(draftFreightFrom(null)).toEqual({ amount: "", gstSlab: null });
    expect(draftFreightFrom(freight)).toEqual({ amount: "2000", gstSlab: null });
    expect(draftFreightFrom({ ...freight, gstSlabChosen: true })).toEqual({
      amount: "2000",
      gstSlab: "18",
    });
  });
});
