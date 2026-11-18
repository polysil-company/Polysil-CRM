import { afterEach, describe, expect, it } from "vitest";

import { createQuotation, previewQuoteLines } from "@/features/quotations/api/quotations.api";
import { patchSettings } from "@/features/settings/api/settings.api";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { mockDb, resetMockDb } from "@/mocks/db";

import { createOrder, submitOrder } from "./orders.api";
import type { CreateDirectOrder } from "./orders.schemas";

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

let keys = 0;
function key(): string {
  keys += 1;
  return `export-sample-${String(keys)}`;
}

function qualifiedLead(): { id: string; territoryId: string } {
  const lead = mockDb.leads.find((item) => item.stage === "qualified");
  if (lead === undefined) throw new Error("No qualified lead");
  return { id: lead.id, territoryId: lead.territory.id };
}

const LINE = {
  product_id: MOCK_PRODUCTS[0]?.id ?? "",
  qty: "10",
  discount_pct: "0",
  discount2_pct: "0",
  discount3_pct: "0",
};

function direct(overrides: Partial<CreateDirectOrder> = {}): CreateDirectOrder {
  const lead = qualifiedLead();
  return {
    order_type: "export",
    export_country: "Kenya",
    lead_id: lead.id,
    party: { name: "Nairobi Agro Ltd", mobile: null, address: null, gstin: null },
    place_of_supply_territory_id: lead.territoryId,
    delivery_address: null,
    payment_terms: "full_payment",
    remarks: null,
    lines: [LINE],
    ...overrides,
  };
}

/** A sample: typed lines, no country. */
function sample(): CreateDirectOrder {
  const { export_country: _country, ...rest } = direct({ order_type: "sample" });
  return rest;
}

describe("[SO-010] Export orders (contract)", () => {
  afterEach(reset);

  it("prices an export under the LUT at 0 % IGST, never intra-state, and takes the LUT at submit", async () => {
    reset();
    const order = await createOrder({ body: direct(), idempotencyKey: key() });
    expect(order).toMatchObject({
      orderType: "export",
      taxTreatment: "export_lut",
      exportCountry: "Kenya",
      lutArn: null,
      intraState: false,
    });
    expect(order.totals.igst).toBe("0.00");
    expect(order.totals.cgst).toBe("0.00");
    expect(order.totals.total).toBe(order.totals.taxable);

    const submitted = await submitOrder(order.id, {
      body: { expected_status: "draft" },
      idempotencyKey: key(),
    });
    expect(submitted.lutArn).toBe("AD2404260012345");
  });

  it("charges IGST at the slab when the setting says so", async () => {
    reset();
    await patchSettings({ values: { export_tax_treatment: "igst" } });
    const order = await createOrder({ body: direct(), idempotencyKey: key() });
    expect(order.taxTreatment).toBe("export_igst");
    expect(Number(order.totals.igst)).toBeGreaterThan(0);
    expect(order.totals.cgst).toBe("0.00");
  });

  it("needs the country, refuses a GSTIN, and is for staff only", async () => {
    reset();
    await expect(
      createOrder({ body: direct({ export_country: "" }), idempotencyKey: key() }),
    ).rejects.toMatchObject({ status: 422, code: "export_country_required" });
    await expect(
      createOrder({
        body: direct({
          party: {
            name: "Nairobi Agro Ltd",
            mobile: null,
            address: null,
            gstin: "24AAACP1234A1Z5",
          },
        }),
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 422, code: "export_party_gstin" });
    await expect(
      createOrder({
        body: direct({ order_type: "commercial", export_country: "Kenya" }),
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 422, code: "export_country_not_export" });
    writeMockRole("dealer");
    await expect(createOrder({ body: direct(), idempotencyKey: key() })).rejects.toMatchObject({
      status: 403,
      code: "type_staff_only",
    });
  });

  it("refuses to submit an export under the LUT when no LUT covers the day", async () => {
    reset();
    for (const registration of mockDb.sellerGstins) registration.luts = [];
    const order = await createOrder({ body: direct(), idempotencyKey: key() });
    await expect(
      submitOrder(order.id, { body: { expected_status: "draft" }, idempotencyKey: key() }),
    ).rejects.toMatchObject({ status: 422, code: "lut_missing" });
  });

  it("previews an export with the tax it will store", async () => {
    reset();
    const lead = qualifiedLead();
    const preview = await previewQuoteLines({
      place_of_supply_territory_id: lead.territoryId,
      lines: [LINE],
      tax_treatment: "export_lut",
    });
    expect(preview.intraState).toBe(false);
    expect(preview.totals.total).toBe(preview.totals.taxable);
  });
});

describe("[SO-010] Export quotations (contract)", () => {
  afterEach(reset);

  it("makes an export quotation with its country and LUT, and refuses one without a country", async () => {
    reset();
    const lead = qualifiedLead();
    const base = {
      lead_id: lead.id,
      sales_type: "export" as const,
      party: { name: "Nairobi Agro Ltd", mobile: "9876543210", address: null, gstin: null },
      terms: null,
      lines: [LINE],
    };
    await expect(createQuotation({ body: base, idempotencyKey: key() })).rejects.toMatchObject({
      status: 422,
      code: "export_country_required",
    });
    const quotation = await createQuotation({
      body: { ...base, export_country: "Kenya" },
      idempotencyKey: key(),
    });
    expect(quotation).toMatchObject({
      salesType: "export",
      taxTreatment: "export_lut",
      exportCountry: "Kenya",
      lutArn: "AD2404260012345",
      intraState: false,
    });
  });
});

describe("[SO-010] Sample orders (contract)", () => {
  afterEach(reset);

  it("gives a free sample every line 100 % off, and still submits it on its list value", async () => {
    reset();
    const order = await createOrder({
      body: sample(),
      idempotencyKey: key(),
    });
    expect(order.samplePricing).toBe("free");
    expect(order.totals.total).toBe("0.00");
    expect(order.lines.every((line) => line.total === "0.00")).toBe(true);
    const submitted = await submitOrder(order.id, {
      body: { expected_status: "draft" },
      idempotencyKey: key(),
    });
    expect(submitted.status).toBe("submitted");
  });

  it("prices a charged sample like a commercial order", async () => {
    reset();
    await patchSettings({ values: { sample_pricing: "charged" } });
    const order = await createOrder({
      body: sample(),
      idempotencyKey: key(),
    });
    expect(order.samplePricing).toBe("charged");
    expect(Number(order.totals.total)).toBeGreaterThan(0);
  });

  it("refuses a sample worth more than the limit at list price", async () => {
    reset();
    await patchSettings({ values: { sample_max_value: 1 } });
    await expect(
      createOrder({
        body: sample(),
        idempotencyKey: key(),
      }),
    ).rejects.toMatchObject({ status: 422, code: "sample_over_limit" });
  });
});
