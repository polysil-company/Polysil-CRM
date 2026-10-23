import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { createOrder } from "@/features/orders/api/orders.api";
import { createQuotation } from "@/features/quotations/api/quotations.api";
import { QuotationDetail } from "@/features/quotations/components/quotation-detail";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { MOCK_PRODUCTS } from "@/mocks/data/quotations";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { sampleHint } from "./order-builder";
import { NewDirectOrder } from "./order-builder-pages";
import { OrderDetail } from "./order-detail";

const push = vi.fn();

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push, back: vi.fn() }),
}));

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
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

let keys = 0;
function key(): string {
  keys += 1;
  return `export-sample-ui-${String(keys)}`;
}

describe("[SO-010] sampleHint", () => {
  it("says what the sample setting makes of a sample", () => {
    expect(sampleHint("free", null)).toMatch(/100 % off/);
    expect(sampleHint("charged", 50_000)).toMatch(
      /Priced like a commercial order\. It may be worth up to ₹50,000/,
    );
  });
});

describe("[SO-010] The order builder's export and sample", () => {
  afterEach(() => {
    push.mockReset();
    resetMockDb();
  });

  it("asks an export for the buyer's country in place of the GSTIN", async () => {
    resetMockDb();
    signInAs("admin");
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <NewDirectOrder leadId={qualifiedLead().id} />
        <Toaster />
      </>,
    );
    await screen.findByRole("form", { name: "New order" });
    expect(screen.getByLabelText(/GSTIN/)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Export" }));
    expect(await screen.findByLabelText("Country")).toBeInTheDocument();
    expect(screen.queryByLabelText(/GSTIN/)).toBeNull();
    expect(
      screen.getByText(/Export under a LUT, no IGST, fixed when the draft is saved/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Sample" }));
    expect(await screen.findByText(/A free sample: every line is 100 % off/)).toBeInTheDocument();
  });

  it("offers a dealer no export or sample", async () => {
    resetMockDb();
    signInAs("dealer");
    renderWithProviders(<NewDirectOrder leadId={null} />);
    await screen.findByRole("form", { name: "New order" });
    expect(screen.queryByRole("radio", { name: "Export" })).toBeNull();
    expect(screen.queryByRole("radio", { name: "Sample" })).toBeNull();
  });
});

describe("[SO-010] An export or sample on its page", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("shows an export order's country and tax, and a free sample on each line", async () => {
    resetMockDb();
    signInAs("admin");
    const lead = qualifiedLead();
    const base = {
      lead_id: lead.id,
      party: { name: "Nairobi Agro Ltd", mobile: null, address: null, gstin: null },
      place_of_supply_territory_id: lead.territoryId,
      delivery_address: null,
      payment_terms: "full_payment" as const,
      remarks: null,
      lines: [LINE],
    };
    const exported = await createOrder({
      body: { ...base, order_type: "export", export_country: "Kenya" },
      idempotencyKey: key(),
    });
    const { unmount } = renderWithProviders(<OrderDetail orderId={exported.id} />);
    expect(await screen.findByText("Kenya")).toBeInTheDocument();
    expect(screen.getByText("Export under a LUT, no IGST")).toBeInTheDocument();
    expect(screen.getByText("The LUT is taken when the order is submitted.")).toBeInTheDocument();
    unmount();

    const sample = await createOrder({
      body: { ...base, order_type: "sample" },
      idempotencyKey: key(),
    });
    renderWithProviders(<OrderDetail orderId={sample.id} />);
    expect((await screen.findAllByText("Free sample")).length).toBeGreaterThan(1);
  });

  it("shows an export quotation's country and LUT", async () => {
    resetMockDb();
    signInAs("admin");
    const quotation = await createQuotation({
      body: {
        lead_id: qualifiedLead().id,
        sales_type: "export",
        export_country: "Kenya",
        party: { name: "Nairobi Agro Ltd", mobile: "9876543210", address: null, gstin: null },
        terms: null,
        lines: [LINE],
      },
      idempotencyKey: key(),
    });
    renderWithProviders(<QuotationDetail quotationId={quotation.id} />);
    expect(await screen.findByText("Kenya")).toBeInTheDocument();
    expect(screen.getByText("Export under a LUT, no IGST")).toBeInTheDocument();
    expect(screen.getByText("AD2404260012345")).toBeInTheDocument();
  });
});
