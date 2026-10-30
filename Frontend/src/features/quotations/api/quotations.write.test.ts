import { afterEach, describe, expect, it } from "vitest";

import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { isApiError } from "@/lib/api/errors";
import { mockDb, resetMockDb } from "@/mocks/db";

import {
  createQuotation,
  getGstSlabChoices,
  patchQuotation,
  previewQuoteLines,
  replaceQuotationLines,
  searchProducts,
} from "./quotations.api";
import type { CreateQuotationRequest, QuotationLineRequest } from "./quotations.schemas";

function leadAt(stage: LeadStage): string {
  const lead = mockDb.leads.find((item) => item.stage === stage);
  if (lead === undefined) {
    throw new Error(`No ${stage} lead in the mock database`);
  }
  return lead.id;
}

function draftId(): string {
  const draft = mockDb.quotations.find(
    (quotation) => quotation.status === "draft" && quotation.lead !== null,
  );
  if (draft === undefined) {
    throw new Error("No draft in the mock database");
  }
  return draft.id;
}

function sentId(): string {
  const sent = mockDb.quotations.find((quotation) => quotation.status === "sent");
  if (sent === undefined) {
    throw new Error("No sent quotation in the mock database");
  }
  return sent.id;
}

async function firstProductLine(qty = "12"): Promise<QuotationLineRequest> {
  const [product] = await searchProducts("pipe");
  if (product === undefined) {
    throw new Error("No pipe in the mock catalogue");
  }
  return {
    product_id: product.id,
    qty,
    discount_pct: "10",
    discount2_pct: "5",
    discount3_pct: "0",
  };
}

/** A create request for `leadId` with the party filled as the builder would. */
function createBody(
  leadId: string,
  lines: readonly QuotationLineRequest[],
): CreateQuotationRequest {
  return {
    lead_id: leadId,
    sales_type: "commercial",
    party: { name: "Ramesh Patel", mobile: "+919876543210", address: null, gstin: null },
    terms: null,
    lines,
  };
}

/** What the call was refused with, or a failure when it wasn't refused. */
async function refusal(call: Promise<unknown>): Promise<{ status: number; code: string | null }> {
  try {
    await call;
  } catch (error) {
    if (isApiError(error)) {
      return { status: error.status ?? 0, code: error.code ?? null };
    }
    throw error;
  }
  throw new Error("Expected the call to be refused");
}

describe("[MSTR-003] searchProducts", () => {
  it("finds active products by description, with unit and HSN", async () => {
    const products = await searchProducts("pipe");

    expect(products.length).toBeGreaterThan(0);
    expect(products.every((product) => product.description.toLowerCase().includes("pipe"))).toBe(
      true,
    );
    expect(products[0]).toMatchObject({ uom: expect.any(String), hsnCode: expect.any(String) });
  });

  it("returns nothing for a description no product has", async () => {
    await expect(searchProducts("zzz-no-such-product")).resolves.toEqual([]);
  });
});

describe("[QUOT-005] previewQuoteLines", () => {
  it("prices a basket with its tiers, tax split and totals", async () => {
    const line = await firstProductLine();
    const preview = await previewQuoteLines({
      place_of_supply_territory_id: "t-1",
      lines: [line],
    });

    expect(preview.lines).toHaveLength(1);
    const [priced] = preview.lines;
    expect(priced?.discounts.map((tier) => Number(tier.pct))).toEqual([10, 5, 0]);
    expect(priced?.cgst.amount).toBe(priced?.sgst.amount);
    expect(preview.totals.total).toBe(priced?.total);
    expect(priced?.priceListItemId).toEqual(expect.any(String));
  });
});

describe("[QUOT-004] createQuotation", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("saves a draft with no number on a qualified lead", async () => {
    const line = await firstProductLine();
    const body = createBody(leadAt("qualified"), [line]);

    const draft = await createQuotation({ body, idempotencyKey: "create-1" });

    expect(draft).toMatchObject({ status: "draft", quoteNo: null });
    expect(draft.lines).toHaveLength(1);
    // The same key and body replays the same draft rather than making another.
    await expect(createQuotation({ body, idempotencyKey: "create-1" })).resolves.toMatchObject({
      id: draft.id,
    });
  });

  it("refuses a lead that has not been qualified", async () => {
    await expect(
      refusal(createQuotation({ body: createBody(leadAt("new"), []), idempotencyKey: "k" })),
    ).resolves.toEqual({ status: 422, code: "lead_not_qualified" });
  });

  it("refuses a basket priced on a price list that has since changed", async () => {
    const line = await firstProductLine();
    const preview = await previewQuoteLines({ place_of_supply_territory_id: "t-1", lines: [line] });
    const priceListItemId = preview.lines[0]?.priceListItemId;
    if (priceListItemId === undefined) {
      throw new Error("The preview priced no line");
    }
    mockDb.priceVersion += 1;

    await expect(
      refusal(
        createQuotation({
          body: createBody(leadAt("qualified"), [{ ...line, price_list_item_id: priceListItemId }]),
          idempotencyKey: "stale",
        }),
      ),
    ).resolves.toEqual({ status: 409, code: "rate_changed" });
  });
});

describe("[QUOT-004] editing a draft", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("changes the header and replaces the lines", async () => {
    const id = draftId();
    const line = await firstProductLine("30");

    const patched = await patchQuotation(id, {
      body: { terms: "Delivery in 7 days", expected_status: "draft" },
      idempotencyKey: "patch-1",
    });
    expect(patched.terms).toBe("Delivery in 7 days");

    const replaced = await replaceQuotationLines(id, {
      body: { lines: [line, line], expected_status: "draft" },
      idempotencyKey: "lines-1",
    });
    expect(replaced.lines.map((item) => item.lineNo)).toEqual([1, 2]);
    expect(replaced.terms).toBe("Delivery in 7 days");
  });

  it("refuses to edit a quotation that has been sent", async () => {
    const result = await refusal(
      replaceQuotationLines(sentId(), {
        body: { lines: [], expected_status: "draft" },
        idempotencyKey: "lines-sent",
      }),
    );

    expect(result.status).toBe(409);
    expect(["status_changed", "quotation_not_draft"]).toContain(result.code);
  });
});

describe("[QUOT-015] GST slabs and freight, through the API", () => {
  afterEach(() => {
    resetMockDb();
  });

  /** The 422's code and fields, from a refused preview. */
  async function refusal(promise: Promise<unknown>): Promise<{ code: string; fields: unknown }> {
    try {
      await promise;
    } catch (error) {
      if (isApiError(error)) {
        const details = error.details;
        const fields =
          typeof details === "object" && details !== null && "fields" in details
            ? details.fields
            : null;
        return { code: error.code ?? "", fields };
      }
      throw error;
    }
    throw new Error("The preview was not refused");
  }

  it("reads the slabs on offer", async () => {
    expect(await getGstSlabChoices()).toEqual(["0", "5", "18", "40"]);
  });

  it("prices a picked slab and freight, which joins taxable and total but not gross", async () => {
    const line = await firstProductLine("10");
    const plain = await previewQuoteLines({
      place_of_supply_territory_id: "t-1",
      sales_type: "commercial",
      lines: [line],
    });
    const preview = await previewQuoteLines({
      place_of_supply_territory_id: "t-1",
      sales_type: "commercial",
      lines: [{ ...line, gst_slab: "5" }],
      freight: { amount: "1000" },
    });

    const [priced] = preview.lines;
    expect(priced).toMatchObject({ gstSlab: "5.000", gstSlabChosen: true });
    expect(priced?.hsnSlab).toBe(plain.lines[0]?.gstSlab);
    // Without a slab, freight takes the highest among the lines: here the picked 5 %.
    expect(preview.freight).toMatchObject({
      amount: "1000.00",
      gstSlab: "5.000",
      total: "1050.00",
    });
    expect(preview.totals.gross).toBe(plain.totals.gross);
    expect(preview.totals.freight).toBe("1000.00");
    expect(Number(preview.totals.taxable)).toBeCloseTo(Number(plain.totals.taxable) + 1000, 2);
  });

  it("refuses a slab or freight on a type that takes neither", async () => {
    const line = await firstProductLine("10");
    expect(
      await refusal(
        previewQuoteLines({
          place_of_supply_territory_id: "t-1",
          sales_type: "subsidised",
          lines: [{ ...line, gst_slab: "5" }],
        }),
      ),
    ).toMatchObject({
      code: "gst_choice_not_allowed",
      fields: { "lines[0].gst_slab": expect.any(String) },
    });
    expect(
      await refusal(
        previewQuoteLines({
          place_of_supply_territory_id: "t-1",
          sales_type: "subsidised",
          lines: [line],
          freight: { amount: "100" },
        }),
      ),
    ).toMatchObject({ code: "freight_not_allowed", fields: { freight: expect.any(String) } });
  });

  it("refuses a slab off the list and a freight amount that isn't rupees", async () => {
    const line = await firstProductLine("10");
    expect(
      await refusal(
        previewQuoteLines({
          place_of_supply_territory_id: "t-1",
          sales_type: "industrial",
          lines: [{ ...line, gst_slab: "28" }],
        }),
      ),
    ).toMatchObject({ code: "gst_slab_not_offered" });
    expect(
      await refusal(
        previewQuoteLines({
          place_of_supply_territory_id: "t-1",
          sales_type: "industrial",
          lines: [line],
          freight: { amount: "12.345" },
        }),
      ),
    ).toMatchObject({
      code: "freight_amount_invalid",
      fields: { "freight.amount": expect.any(String) },
    });
  });
});
