import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type * as NextNavigation from "next/navigation";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { QuotationDetail } from "@/features/quotations/components/quotation-detail";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole, writeMockScenario } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { DispatchQueue } from "./dispatch-queue";
import { OrderDetail } from "./order-detail";
import { OrdersTable } from "./orders-table";
import { OrdersToolbar } from "./orders-toolbar";

const push = vi.fn();

vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof NextNavigation>()),
  useRouter: () => ({ push }),
}));

/** The screen reads the session; the mock backend checks the stored role. Both are set. */
function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

function seeded(status: string): string {
  const order = mockDb.orders.find((item) => item.status === status);
  if (order === undefined) {
    throw new Error(`No ${status} order in the mock`);
  }
  return order.id;
}

function showOrder(orderId: string): ReturnType<typeof userEvent.setup> {
  const user = userEvent.setup();
  renderWithProviders(
    <>
      <OrderDetail orderId={orderId} />
      <Toaster />
    </>,
  );
  return user;
}

function reset(): void {
  resetMockDb();
  writeMockRole("state_manager");
  writeMockScenario("realistic");
  push.mockReset();
}

describe("[SO-001] Sales orders list", () => {
  afterEach(reset);

  it("lists orders with their status, whom they wait on and how much has shipped", async () => {
    signInAs("state_manager");
    renderWithProviders(
      <>
        <OrdersToolbar />
        <OrdersTable />
      </>,
    );

    const table = await screen.findByRole("table", { name: "Sales orders" });
    expect(within(table).getAllByRole("row")).toHaveLength(mockDb.orders.length + 1);
    expect(within(table).getAllByText("Waiting for approval").length).toBeGreaterThan(0);
    expect(within(table).getAllByText(/^Waiting on /).length).toBeGreaterThan(0);
    expect(within(table).getByText("100%")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Only my orders" })).not.toBeChecked();
  });

  it("filters from the URL, and says so when nothing matches", async () => {
    signInAs("state_manager");
    renderWithProviders(<OrdersTable />, { searchParams: "?status=cancelled&q=nobody-at-all" });

    expect(await screen.findByText("No orders match these filters")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear filters" })).toBeInTheDocument();
  });

  it("explains where orders come from when there are none", async () => {
    signInAs("state_manager");
    writeMockScenario("empty");
    renderWithProviders(<OrdersTable />);

    expect(await screen.findByText("No sales orders yet")).toBeInTheDocument();
  });
});

describe("[SO-002] OrderDetail", () => {
  afterEach(reset);

  it("shows the chain, what has shipped and each dispatch — with no dispatch actions for a manager", async () => {
    signInAs("state_manager");
    showOrder(seeded("partially_dispatched"));

    const steps = await screen.findByRole("list", { name: "Approval steps, in order" });
    expect(within(steps).getByText(/Accounts/)).toBeInTheDocument();
    expect(within(steps).getByText(/Dispatch$/)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Sent" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Dispatches, newest first" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open PDF" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Record dispatch" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Void…" })).not.toBeInTheDocument();
  });
});

describe("[SO-004] Submit a returned order again", () => {
  afterEach(reset);

  it("shows why it came back, then submits it into the chain", async () => {
    signInAs("admin");
    const user = showOrder(seeded("draft"));

    expect(await screen.findByText(/^Returned by District Manager/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Submit again" }));
    const dialog = await screen.findByRole("dialog", { name: "Submit again for approval?" });
    await user.click(within(dialog).getByRole("button", { name: "Submit" }));

    expect(await screen.findByText(/submitted$/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("Waiting for approval").length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/^Waiting now/)).toBeInTheDocument();
  });
});

describe("[DISP-002] Record a dispatch", () => {
  afterEach(reset);

  it("checks the quantities, then records what left and moves the order on", async () => {
    signInAs("dispatch_manager");
    const user = showOrder(seeded("partially_dispatched"));

    await user.click(await screen.findByRole("button", { name: "Record dispatch" }));
    const dialog = await screen.findByRole("dialog", { name: "Record a dispatch" });
    await user.click(within(dialog).getByRole("button", { name: "Record dispatch" }));
    expect(
      await within(dialog).findByText("Enter what left for at least one item"),
    ).toBeInTheDocument();

    await user.type(within(dialog).getAllByRole("textbox")[0] ?? dialog, "9999");
    await user.click(within(dialog).getByRole("button", { name: "Record dispatch" }));
    expect(await within(dialog).findByText("More than is still open")).toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: "Everything open" }));
    await user.type(within(dialog).getByLabelText(/Challan number/), "DC-77");
    await user.click(within(dialog).getByRole("button", { name: "Record dispatch" }));

    expect(await screen.findByText(/^D\/.+ recorded$/)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("Dispatched").length).toBeGreaterThan(0);
    });
  });
});

describe("[SO-003] Place an order from an accepted quotation", () => {
  afterEach(reset);

  it("makes a draft order and opens it; a quotation already ordered links to its order", async () => {
    signInAs("employee");
    const taken = new Set(
      mockDb.orders.flatMap((order) => order.quotations.map((item) => item.id)),
    );
    const free = mockDb.quotations.find(
      (item) => item.status === "accepted" && item.superseded_by === null && !taken.has(item.id),
    );
    if (free === undefined) throw new Error("Every accepted quotation is on an order");
    const user = userEvent.setup();
    const view = renderWithProviders(
      <>
        <QuotationDetail quotationId={free.id} />
        <Toaster />
      </>,
    );

    const place = await screen.findByRole("button", { name: "Place order" });
    await waitFor(() => {
      expect(place).toBeEnabled();
    });
    await user.click(place);
    const dialog = await screen.findByRole("dialog", { name: "Place an order" });
    expect(within(dialog).getByRole("radio", { name: "Full payment" })).toBeChecked();
    await user.click(within(dialog).getByRole("button", { name: "Make draft order" }));
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith(expect.stringMatching(/^\/sales-orders\//));
    });
    view.unmount();

    const ordered = mockDb.orders.find(
      (order) => order.status !== "cancelled" && order.quotations.length > 0,
    );
    const quotationId = ordered?.quotations[0]?.id ?? "";
    renderWithProviders(<QuotationDetail quotationId={quotationId} />);
    expect(await screen.findByRole("link", { name: /^Open order/ })).toHaveAttribute(
      "href",
      `/sales-orders/${ordered?.id ?? ""}`,
    );
  });
});

describe("[DISP-001] Dispatch queue", () => {
  afterEach(reset);

  it("lists approved orders still to ship, each opening its order ready to record", async () => {
    signInAs("dispatch_manager");
    renderWithProviders(<DispatchQueue />);

    const list = await screen.findByRole("list", { name: "Orders to ship" });
    const rows = within(list).getAllByRole("listitem");
    const waiting = mockDb.orders.filter(
      (order) => order.status === "approved" || order.status === "partially_dispatched",
    );
    expect(rows).toHaveLength(waiting.length);
    expect(screen.getByText(`${String(waiting.length)} orders still to ship.`)).toBeInTheDocument();
    const [first] = rows;
    const record = await within(first ?? list).findByRole("link", {
      name: /^Record a dispatch on /,
    });
    expect(record.getAttribute("href")).toMatch(/^\/sales-orders\/.+\?record=dispatch$/);
    expect(within(first ?? list).getByText(/% sent$/)).toBeInTheDocument();
  });

  it("offers no recording to someone who can only look", async () => {
    signInAs("state_manager");
    renderWithProviders(<DispatchQueue />);

    await screen.findByRole("list", { name: "Orders to ship" });
    expect(screen.queryByRole("link", { name: /^Record a dispatch/ })).not.toBeInTheDocument();
  });

  it("shows the dispatch log, and keeps the tab and days in the URL", async () => {
    signInAs("dispatch_manager");
    const user = userEvent.setup();
    const onUrlChange = vi.fn<(queryString: string) => void>();
    renderWithProviders(<DispatchQueue />, { onUrlChange });
    await screen.findByRole("list", { name: "Orders to ship" });

    await user.click(screen.getByRole("button", { name: "Dispatched" }));
    const log = await screen.findByRole("list", { name: "Dispatches, newest first" });
    expect(within(log).getAllByRole("listitem").length).toBeGreaterThan(0);
    expect(onUrlChange).toHaveBeenLastCalledWith(expect.stringContaining("tab=dispatched"));

    await user.type(screen.getByLabelText("From"), "2001-01-01");
    await user.type(screen.getByLabelText("to"), "2001-01-02");
    expect(await screen.findByText("Nothing sent on these days")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Any day" }));
    expect(await screen.findByRole("list", { name: "Dispatches, newest first" })).toBeVisible();
  });
});

describe("[DISP-002] Record a dispatch from the queue's link", () => {
  afterEach(reset);

  it("opens the form at once when the order is reached with ?record=dispatch", async () => {
    signInAs("dispatch_manager");
    renderWithProviders(<OrderDetail orderId={seeded("approved")} />, {
      searchParams: "?record=dispatch",
    });

    expect(await screen.findByRole("dialog", { name: "Record a dispatch" })).toBeVisible();
  });

  it("ignores the link for someone who may not record", async () => {
    signInAs("state_manager");
    renderWithProviders(<OrderDetail orderId={seeded("approved")} />, {
      searchParams: "?record=dispatch",
    });

    await screen.findByRole("heading", { level: 2 });
    expect(screen.queryByRole("dialog", { name: "Record a dispatch" })).not.toBeInTheDocument();
  });
});
