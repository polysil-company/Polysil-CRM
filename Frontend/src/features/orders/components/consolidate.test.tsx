import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import type { QuotationWire } from "@/features/quotations/api/quotations.schemas";
import { QuotationDetail } from "@/features/quotations/components/quotation-detail";
import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole, writeMockScenario } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

const push = vi.fn();

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push }),
}));

const DEALER = { id: "prt-201", name: "Shah Agro Traders", partner_type: "dealer" };

function reset(): void {
  resetMockDb();
  writeMockRole("state_manager");
  writeMockScenario("realistic");
  push.mockReset();
}

function signIn(): void {
  writeMockRole("employee");
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor("employee"))));
}

/** Two accepted quotations on different leads, not yet ordered, both through one dealer. */
function twoOfOneDealer(): [QuotationWire, QuotationWire] {
  const taken = new Set(mockDb.orders.flatMap((order) => order.quotations.map((item) => item.id)));
  const free = mockDb.quotations.filter(
    (item) =>
      item.status === "accepted" &&
      item.superseded_by === null &&
      item.sales_type !== "subsidised" &&
      item.sales_type !== "export" &&
      !taken.has(item.id),
  );
  const [first] = free;
  const second = free.find((item) => item.lead?.id !== first?.lead?.id);
  if (first === undefined || second === undefined) throw new Error("Mock quotations changed.");
  first.partner = DEALER;
  second.partner = DEALER;
  second.place_of_supply = first.place_of_supply;
  return [first, second];
}

async function openPlaceOrder(quotationId: string): Promise<{
  user: ReturnType<typeof userEvent.setup>;
  dialog: HTMLElement;
}> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <QuotationDetail quotationId={quotationId} />
      <Toaster />
    </>,
  );
  const place = await screen.findByRole("button", { name: "Place order" });
  await waitFor(() => {
    expect(place).toBeEnabled();
  });
  await user.click(place);
  return { user, dialog: await screen.findByRole("dialog", { name: "Place an order" }) };
}

describe("[SO-011] A consolidated order from several quotations of one dealer", () => {
  afterEach(reset);

  it("adds the dealer's other accepted quotations and makes one order of them", async () => {
    signIn();
    const [first, second] = twoOfOneDealer();
    const { user, dialog } = await openPlaceOrder(first.id);

    const others = await within(dialog).findByRole("list", { name: "Other accepted quotations" });
    const box = within(others).getByRole("checkbox", { name: new RegExp(second.quote_no ?? "") });
    await user.click(box);
    expect(within(dialog).getByText(/^2 quotations, /)).toHaveTextContent(
      "the order is consolidated: Shah Agro Traders is the party",
    );
    await user.click(within(dialog).getByRole("button", { name: "Make draft order" }));
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/sales-orders\//));
    });
    const made = mockDb.orders[0];
    expect(made?.quotations.map((item) => item.id).sort()).toEqual([first.id, second.id].sort());
  });

  it("unticks and marks a quotation the backend says is on an order already", async () => {
    signIn();
    const [first, second] = twoOfOneDealer();
    server.use(
      http.post(buildApiUrl("/orders"), () =>
        HttpResponse.json(
          {
            error: {
              code: "quotation_on_order",
              message: "The quotation is already on an order.",
              fields: { quotation_ids: second.id },
            },
          },
          { status: 409 },
        ),
      ),
    );
    const { user, dialog } = await openPlaceOrder(first.id);
    const others = await within(dialog).findByRole("list", { name: "Other accepted quotations" });
    await user.click(
      within(others).getByRole("checkbox", { name: new RegExp(second.quote_no ?? "") }),
    );
    await user.click(within(dialog).getByRole("button", { name: "Make draft order" }));

    expect(
      await within(dialog).findByText("One of the added quotations is on an order already"),
    ).toBeVisible();
    const box = within(others).getByRole("checkbox", { name: new RegExp(second.quote_no ?? "") });
    expect(box).not.toBeChecked();
    expect(box).toHaveAttribute("aria-disabled", "true");
    expect(
      within(others).getByText(
        new RegExp(`${second.lead?.inquiry_no ?? ""} · already on an order`),
      ),
    ).toBeInTheDocument();
  });

  it("names the field when the quotations don't match", async () => {
    signIn();
    const [first, second] = twoOfOneDealer();
    const other = mockDb.quotations.find(
      (item) => item.place_of_supply.territory.id !== first.place_of_supply.territory.id,
    );
    if (other === undefined) throw new Error("Mock places changed.");
    second.place_of_supply = other.place_of_supply;
    const { user, dialog } = await openPlaceOrder(first.id);
    const others = await within(dialog).findByRole("list", { name: "Other accepted quotations" });
    await user.click(
      within(others).getByRole("checkbox", { name: new RegExp(second.quote_no ?? "") }),
    );
    await user.click(within(dialog).getByRole("button", { name: "Make draft order" }));

    expect(await within(dialog).findByText("The quotations don't match")).toBeVisible();
    expect(within(dialog).getByText(/They differ in the place of supply\./)).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("offers nothing to add on a direct quotation", async () => {
    signIn();
    const [first] = twoOfOneDealer();
    first.partner = null;
    const { dialog } = await openPlaceOrder(first.id);
    expect(within(dialog).getByRole("radio", { name: "Full payment" })).toBeChecked();
    expect(within(dialog).queryByText(/other accepted quotations/)).not.toBeInTheDocument();
  });
});
