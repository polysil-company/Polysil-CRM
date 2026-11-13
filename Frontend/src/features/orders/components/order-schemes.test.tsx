import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { cancelOrder, getOrderSchemes, submitOrder } from "@/features/orders/api/orders.api";
import type { OrderWire } from "@/features/orders/api/orders.schemas";
import type { EntitlementWire } from "@/features/schemes/api/schemes.schemas";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole, writeMockScenario } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { OrderDetail } from "./order-detail";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

/** The seeded draft through a dealer (₹15,093 taxable). */
function dealerDraft(): OrderWire {
  const order = mockDb.orders.find(
    (item) => item.status === "draft" && item.partner?.partner_type === "dealer",
  );
  if (order === undefined) throw new Error("No dealer draft in the mock");
  return order;
}

/**
 * Brings two schemes within the draft's reach (GJ-DRIP-5's 5%, Monsoon points) and gives its
 * dealer a ₹3,000 credit, so the preview has a discount, a credit and points.
 */
function withinReach(order: OrderWire): void {
  for (const scheme of mockDb.schemes) {
    if (scheme.code === "GJ-DRIP-5" || scheme.code === "MONSOON-PTS") {
      scheme.condition = { ...scheme.condition, min: "10000.000" };
    }
  }
  const [credit] = mockDb.entitlements;
  if (credit === undefined || order.partner === null) throw new Error("No credit to give");
  const given: EntitlementWire = {
    ...credit,
    id: "credit-for-the-draft",
    status: "available",
    partner: { id: order.partner.id, name: order.partner.name },
  };
  mockDb.entitlements.push(given);
}

let keys = 0;
function key(): string {
  keys += 1;
  return `order-schemes-test-${String(keys)}`;
}

describe("[SCHM-005] Scheme benefits on an order — the contract", () => {
  beforeEach(() => {
    writeMockRole("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
    writeMockScenario("realistic");
  });

  it("previews a draft's discount, credit and points, and the payable", async () => {
    const order = dealerDraft();
    withinReach(order);

    const preview = await getOrderSchemes(order.id);

    // 5% of the ₹15,093 taxable value; the ₹3,000 credit; Monsoon's 200 points on delivery.
    expect(preview.discounts).toEqual([
      {
        scheme: expect.objectContaining({ code: "GJ-DRIP-5" }),
        basis: "15093.00",
        amount: "754.65",
      },
    ]);
    expect(preview.credits).toEqual([
      expect.objectContaining({ entitlementId: "credit-for-the-draft", amount: "3000.00" }),
    ]);
    expect(preview.onDelivery).toEqual([expect.objectContaining({ kind: "points", points: 200 })]);
    expect(preview.totalBenefit).toBe("3754.65");
    const total = Math.round(Number(order.totals.total) * 100);
    expect(preview.payable).toBe(((total - 375_465) / 100).toFixed(2));
  });

  it("stores the benefits at submit, refuses the preview after, and reverses them on cancel", async () => {
    const order = dealerDraft();
    withinReach(order);

    const submitted = await submitOrder(order.id, {
      body: { expected_status: "draft" },
      idempotencyKey: key(),
    });
    expect(submitted.benefits.map((benefit) => [benefit.kind, benefit.amount])).toEqual([
      ["discount", "754.65"],
      ["entitlement_used", "3000.00"],
    ]);
    expect(Number(submitted.payable)).toBeCloseTo(Number(order.totals.total) - 3754.65, 2);
    expect(mockDb.entitlements.find((item) => item.id === "credit-for-the-draft")?.status).toBe(
      "consumed",
    );

    const refused = await getOrderSchemes(order.id).catch((error: unknown) => error);
    expect(isApiError(refused) ? refused.code : null).toBe("order_not_draft");

    const cancelled = await cancelOrder(order.id, {
      body: { remark: "Dealer withdrew", expected_status: "submitted" },
      idempotencyKey: key(),
    });
    expect(cancelled.benefits.every((benefit) => benefit.status === "reversed")).toBe(true);
    expect(mockDb.entitlements.find((item) => item.id === "credit-for-the-draft")?.status).toBe(
      "available",
    );
  });
});

describe("[SCHM-005] Scheme benefits on an order — the screen", () => {
  beforeEach(() => {
    signInAs("admin");
  });
  afterEach(() => {
    resetMockDb();
    writeMockRole("state_manager");
    writeMockScenario("realistic");
  });

  it("shows a draft what submit would take off, what delivery earns, and To pay", async () => {
    const order = dealerDraft();
    withinReach(order);
    renderWithProviders(<OrderDetail orderId={order.id} />);

    const card = await screen.findByRole("region", { name: "Schemes" });
    const off = await within(card).findByRole("region", { name: "Taken off at submit" });
    expect(within(off).getByText("Scheme discount")).toBeInTheDocument();
    expect(within(off).getByText("−₹754.65")).toBeInTheDocument();
    expect(within(off).getByText("Credit used")).toBeInTheDocument();
    const earned = within(card).getByRole("region", { name: "Earned on delivery" });
    expect(within(earned).getByText("200 points")).toBeInTheDocument();
    const toPay = within(card).getByRole("group", { name: "To pay" });
    expect(within(toPay).getByText("To pay, once submitted")).toBeInTheDocument();
    expect(within(toPay).getByText("−₹3,754.65")).toBeInTheDocument();
  });

  it("tells a dealer's draft that no scheme applies as it stands", async () => {
    renderWithProviders(<OrderDetail orderId={dealerDraft().id} />);

    const card = await screen.findByRole("region", { name: "Schemes" });
    expect(
      await within(card).findByText("No scheme applies to this order as it stands."),
    ).toBeInTheDocument();
  });

  it("lists a submitted order's benefits, a reversed one struck through, and To pay", async () => {
    const order = mockDb.orders.find((item) => item.status === "approved");
    if (order === undefined) throw new Error("No approved order");
    const total = Number(order.totals.total);
    order.benefits = [
      {
        id: "benefit-1",
        kind: "discount",
        scheme: { id: "scheme-1", code: "GJ-DRIP-5", name: "Gujarat drip 5% above 2 lakh" },
        amount: "1000.00",
        status: "applied",
        applied_at: "2026-10-16T06:00:00.000Z",
      },
      {
        id: "benefit-2",
        kind: "entitlement_used",
        scheme: { id: "scheme-3", code: "NEXT-3K", name: "₹3,000 off the next order" },
        amount: "3000.00",
        status: "reversed",
        applied_at: "2026-10-12T06:00:00.000Z",
      },
    ];
    order.payable = (total - 1000).toFixed(2);
    renderWithProviders(<OrderDetail orderId={order.id} />);

    const list = await screen.findByRole("list", { name: "Scheme benefits" });
    expect(within(list).getByText("Scheme discount")).toBeInTheDocument();
    expect(within(list).getByText("Reversed")).toBeInTheDocument();
    expect(within(list).getByText("Credit used")).toHaveClass("line-through");
    const toPay = screen.getByRole("group", { name: "To pay" });
    expect(within(toPay).getByText("To pay")).toBeInTheDocument();
    expect(within(toPay).getByText("−₹1,000.00")).toBeInTheDocument();
  });

  it("shows no Schemes card on a submitted order without benefits", async () => {
    const order = mockDb.orders.find((item) => item.status === "submitted");
    if (order === undefined) throw new Error("No submitted order");
    renderWithProviders(<OrderDetail orderId={order.id} />);

    await screen.findByRole("heading", { level: 2 });
    expect(screen.queryByRole("region", { name: "Schemes" })).not.toBeInTheDocument();
  });
});
