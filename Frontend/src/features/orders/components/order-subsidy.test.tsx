import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { createOrder, setOrderSubsidy } from "@/features/orders/api/orders.api";
import type { Order } from "@/features/orders/api/orders.schemas";
import { createQuotation, setQuotationSubsidy } from "@/features/quotations/api/quotations.api";
import type { Quotation } from "@/features/quotations/api/quotations.schemas";
import { QuotationDetail } from "@/features/quotations/components/quotation-detail";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { OrderDetail } from "./order-detail";

const push = vi.fn();
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push }),
}));

let keys = 0;

function nextKey(): string {
  keys += 1;
  return `order-subsidy-test-${String(keys)}`;
}

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function reset(): void {
  resetMockDb();
  writeMockRole("admin");
  push.mockReset();
}

const CALCULATION = {
  system_type: "drip" as const,
  crops: [
    {
      crop: null,
      inter_crop: null,
      area: "1.02",
      crop_spacing: "",
      lateral_spacing: "1.2",
      lines: [],
    },
  ],
  head_lines: [],
};

/** A subsidised quotation on a qualified drip lead in Gujarat, its subsidy calculated. */
async function subsidisedQuotation({ withSubsidy = true } = {}): Promise<Quotation> {
  const lead = mockDb.leads.find((item) => item.stage === "qualified");
  const product = MOCK_PRODUCTS[0];
  if (lead === undefined || product === undefined) throw new Error("No qualified lead or product");
  lead.inquiry_type = "subsidised";
  lead.mis_system = "drip";
  const draft = await createQuotation({
    body: {
      lead_id: lead.id,
      sales_type: "subsidised",
      party: { name: "Ramesh Patel", mobile: "+919876543210", address: null, gstin: null },
      terms: null,
      lines: [
        {
          product_id: product.id,
          qty: "10",
          discount_pct: "0",
          discount2_pct: "0",
          discount3_pct: "0",
        },
      ],
    },
    idempotencyKey: nextKey(),
  });
  return withSubsidy
    ? setQuotationSubsidy(draft.id, {
        body: { category_code: "small_farmer", calculation: CALCULATION },
        idempotencyKey: nextKey(),
      })
    : draft;
}

/** Accepted, as the farmer would accept it once sent. */
function accept(quotation: Quotation): void {
  const stored = mockDb.quotations.find((item) => item.id === quotation.id);
  if (stored === undefined) throw new Error("No quotation");
  stored.status = "accepted";
  stored.quote_no = "QT/GJ/2026/0999";
}

function placeFrom(quotation: Quotation, orderType: "subsidised" | "commercial"): Promise<Order> {
  return createOrder({
    body: {
      order_type: orderType,
      quotation_ids: [quotation.id],
      delivery_address: null,
      payment_terms: "full_payment",
      remarks: null,
    },
    idempotencyKey: nextKey(),
  });
}

async function subsidisedOrder(): Promise<{ order: Order; quotation: Quotation }> {
  const quotation = await subsidisedQuotation();
  accept(quotation);
  return { order: await placeFrom(quotation, "subsidised"), quotation };
}

describe("[SO-008] A subsidised order, through the API", () => {
  afterEach(reset);

  it("takes its subsidy from the accepted subsidised quotation", async () => {
    signInAs("admin");
    const { order, quotation } = await subsidisedOrder();

    expect(order.orderType).toBe("subsidised");
    expect(order.subsidy).toMatchObject({
      materialAmount: quotation.subsidy?.totalCost,
      farmerPayable: quotation.subsidy?.farmerShare,
      materialIsTotal: false,
      farmerPayableIsDerived: false,
      leads: [{ id: quotation.lead?.id }],
    });
    expect(Number(order.subsidy?.subsidyAmount)).toBeGreaterThan(0);
  });

  it("refuses a quotation of the wrong type, one without its subsidy, and a dealer", async () => {
    signInAs("admin");
    const quotation = await subsidisedQuotation();
    accept(quotation);
    await expect(placeFrom(quotation, "commercial")).rejects.toMatchObject({
      status: 422,
      code: "type_mismatch",
    });

    const bare = await subsidisedQuotation({ withSubsidy: false });
    accept(bare);
    await expect(placeFrom(bare, "subsidised")).rejects.toMatchObject({
      status: 422,
      code: "quotation_subsidy_missing",
    });

    signInAs("dealer");
    await expect(placeFrom(quotation, "subsidised")).rejects.toMatchObject({
      status: 403,
      code: "type_staff_only",
    });
  });

  it("changes a draft's amounts: material left out is the order total, payable derived", async () => {
    signInAs("admin");
    const { order } = await subsidisedOrder();
    const leadIds = order.subsidy?.leads.map((lead) => lead.id) ?? [];

    const changed = await setOrderSubsidy(order.id, {
      body: { lead_ids: leadIds, subsidy_amount: "100.00" },
      idempotencyKey: nextKey(),
    });

    expect(changed.subsidy).toMatchObject({
      materialAmount: order.totals.total,
      materialIsTotal: true,
      subsidyAmount: "100.00",
      farmerPayable: (Number(order.totals.total) - 100).toFixed(2),
      farmerPayableIsDerived: true,
    });
  });

  it("refuses a new first lead, a subsidy above the material, and an order not subsidised", async () => {
    signInAs("admin");
    const { order } = await subsidisedOrder();
    const other = mockDb.leads.find(
      (lead) => lead.stage === "qualified" && lead.id !== order.lead?.id,
    );
    if (other === undefined) throw new Error("No second qualified lead");

    await expect(
      setOrderSubsidy(order.id, {
        body: { lead_ids: [other.id], subsidy_amount: "100.00" },
        idempotencyKey: nextKey(),
      }),
    ).rejects.toMatchObject({ status: 422, code: "first_lead_fixed" });
    await expect(
      setOrderSubsidy(order.id, {
        body: { lead_ids: [order.lead?.id ?? ""], material_amount: "50.00", subsidy_amount: "60" },
        idempotencyKey: nextKey(),
      }),
    ).rejects.toMatchObject({
      status: 422,
      code: "subsidy_above_material",
      details: { fields: { "subsidy.subsidy_amount": "60" } },
    });

    const commercial = mockDb.orders.find(
      (item) => item.status === "draft" && item.order_type === "commercial",
    );
    if (commercial === undefined) throw new Error("No commercial draft");
    await expect(
      setOrderSubsidy(commercial.id, {
        body: { lead_ids: [commercial.lead?.id ?? ""], subsidy_amount: "1" },
        idempotencyKey: nextKey(),
      }),
    ).rejects.toMatchObject({ status: 422, code: "order_type_not_subsidised" });
  });
});

describe("[SO-008] Placing a subsidised order", () => {
  afterEach(reset);

  it("fixes the type to subsidised and names the quotation's subsidy", async () => {
    signInAs("admin");
    const quotation = await subsidisedQuotation();
    accept(quotation);
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <QuotationDetail quotationId={quotation.id} />
        <Toaster />
      </>,
    );

    const place = await screen.findByRole("button", { name: "Place order" });
    await waitFor(() => {
      expect(place).toBeEnabled();
    });
    await user.click(place);
    const dialog = await screen.findByRole("dialog", { name: "Place an order" });
    expect(within(dialog).getByText("Subsidised")).toBeInTheDocument();
    expect(within(dialog).queryByRole("radio", { name: "Commercial" })).not.toBeInTheDocument();
    expect(within(dialog).getByText(/^The subsidy comes from the quotation/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Make draft order" }));

    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/sales-orders\//));
    });
    expect(mockDb.orders[0]?.order_type).toBe("subsidised");
  });
});

describe("[SO-008] The subsidy on the order", () => {
  afterEach(reset);

  it("shows the amounts and the lead, and saves new amounts on a draft", async () => {
    signInAs("admin");
    const { order } = await subsidisedOrder();
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <OrderDetail orderId={order.id} />
        <Toaster />
      </>,
    );

    expect(await screen.findByText("The scheme pays")).toBeInTheDocument();
    expect(screen.getByText("The farmer pays")).toBeInTheDocument();
    const leads = screen.getByRole("list", { name: "Leads on this order" });
    expect(within(leads).getByText("(the order's lead)")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Edit the subsidy" }));
    const form = await screen.findByRole("form", { name: "Edit the subsidy" });
    const subsidy = within(form).getByRole("textbox", { name: "Subsidy" });
    await user.clear(subsidy);
    await user.type(subsidy, "100");
    await user.clear(within(form).getByRole("textbox", { name: /^Material amount/ }));
    await user.clear(within(form).getByRole("textbox", { name: /^Farmer payable/ }));
    await user.click(within(form).getByRole("button", { name: "Save the subsidy" }));

    expect(await screen.findByText("Subsidy saved", { selector: "[data-title]" })).toBeVisible();
    expect(await screen.findByText("Material (the order total)")).toBeInTheDocument();
    expect(screen.getByText("The farmer pays (material less subsidy)")).toBeInTheDocument();
  });

  it("says when the farmer payable isn't material less subsidy, and refuses one too high", async () => {
    signInAs("admin");
    const { order } = await subsidisedOrder();
    await setOrderSubsidy(order.id, {
      body: {
        lead_ids: [order.lead?.id ?? ""],
        material_amount: "1000.00",
        subsidy_amount: "600.00",
        farmer_payable: "300.00",
      },
      idempotencyKey: nextKey(),
    });
    const user = userEvent.setup();
    renderWithProviders(<OrderDetail orderId={order.id} />);

    expect(
      await screen.findByText(/The farmer payable isn't the material less the subsidy/),
    ).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Edit the subsidy" }));
    const form = await screen.findByRole("form", { name: "Edit the subsidy" });
    const payable = within(form).getByRole("textbox", { name: /^Farmer payable/ });
    await user.clear(payable);
    await user.type(payable, "2000");
    await user.click(within(form).getByRole("button", { name: "Save the subsidy" }));

    expect(
      await within(form).findByText("The farmer's share is more than the material"),
    ).toBeInTheDocument();
  });
});
