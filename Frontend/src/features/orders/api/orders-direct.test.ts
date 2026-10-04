import { afterEach, describe, expect, it } from "vitest";

import { exportLeads } from "@/features/leads/api/leads.api";
import { exportQuotations } from "@/features/quotations/api/quotations.api";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { mockDb, resetMockDb } from "@/mocks/db";

import { createOrder, exportOrders, patchOrder, replaceOrderLines } from "./orders.api";
import type { CreateDirectOrder } from "./orders.schemas";

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
}

function leadAt(stage: string): { id: string; territoryId: string } {
  const lead = mockDb.leads.find((item) => item.stage === stage);
  if (lead === undefined) throw new Error(`No ${stage} lead`);
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
  const lead = leadAt("qualified");
  return {
    order_type: "commercial",
    lead_id: lead.id,
    party: { name: "Kiritbhai Shah", mobile: "+919876543210", address: null, gstin: null },
    place_of_supply_territory_id: lead.territoryId,
    delivery_address: null,
    payment_terms: "full_payment",
    remarks: null,
    lines: [LINE],
    ...overrides,
  };
}

describe("[SO-005] a direct order", () => {
  afterEach(reset);

  it("creates a draft on a qualified lead, priced line by line, with no quotations", async () => {
    writeMockRole("admin");
    const order = await createOrder({ body: direct(), idempotencyKey: "d-1" });

    expect(order).toMatchObject({ status: "draft", orderNo: null, quotations: [] });
    expect(order.party.name).toBe("Kiritbhai Shah");
    expect(order.lines).toHaveLength(1);
    expect(Number(order.totals.total)).toBeGreaterThan(0);
  });

  it("refuses a lead that isn't qualified, and an order with no party's name", async () => {
    writeMockRole("admin");
    const fresh = leadAt("new");
    await expect(
      createOrder({
        body: direct({ lead_id: fresh.id, place_of_supply_territory_id: fresh.territoryId }),
        idempotencyKey: "d-2",
      }),
    ).rejects.toMatchObject({ status: 422, code: "lead_not_open" });

    await expect(
      createOrder({
        body: direct({ party: { name: "", mobile: null, address: null, gstin: null } }),
        idempotencyKey: "d-3",
      }),
    ).rejects.toMatchObject({ status: 422 });
  });

  it("replaces a draft's lines and changes its party", async () => {
    writeMockRole("admin");
    const order = await createOrder({ body: direct(), idempotencyKey: "d-4" });

    const replaced = await replaceOrderLines(order.id, {
      body: { lines: [LINE, { ...LINE, qty: "4" }], expected_status: "draft" },
      idempotencyKey: "d-5",
    });
    expect(replaced.lines.map((line) => line.lineNo)).toEqual([1, 2]);

    const patched = await patchOrder(order.id, {
      body: {
        party: { name: "Shah Agro", mobile: null, address: null, gstin: null },
        expected_status: "draft",
      },
      idempotencyKey: "d-6",
    });
    expect(patched.party.name).toBe("Shah Agro");
  });

  it("refuses new lines on an order that was submitted", async () => {
    writeMockRole("admin");
    const submitted = mockDb.orders.find((order) => order.status === "submitted");
    if (submitted === undefined) throw new Error("No submitted order");
    await expect(
      replaceOrderLines(submitted.id, {
        body: { lines: [LINE], expected_status: "draft" },
        idempotencyKey: "d-7",
      }),
    ).rejects.toMatchObject({ status: 409 });
  });
});

describe("[SO-006] [LEAD-009] [QUOT-013] Excel exports", () => {
  afterEach(reset);

  it("downloads each list as a dated workbook", async () => {
    writeMockRole("admin");
    const orders = await exportOrders({
      cursor: null,
      pageSize: 25,
      q: "",
      status: [],
      orderType: null,
      mine: false,
      leadId: null,
      quotationId: null,
    });
    expect(orders.filename).toMatch(/^orders-\d{4}-\d{2}-\d{2}\.xlsx$/);

    const leads = await exportLeads({
      cursor: null,
      pageSize: 25,
      q: "",
      stage: [],
      source: null,
      type: null,
      sort: "createdAt",
      order: "desc",
      areas: [],
    });
    expect(leads.filename).toMatch(/^leads-/);

    const quotations = await exportQuotations({
      cursor: null,
      pageSize: 25,
      q: "",
      status: [],
      salesType: null,
      currentOnly: true,
      leadId: null,
    });
    expect(quotations.filename).toMatch(/^quotations-/);
  });
});
