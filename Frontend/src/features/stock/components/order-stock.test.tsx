import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import { createDispatch, getOrder } from "@/features/orders/api/orders.api";
import { NewDirectOrder } from "@/features/orders/components/order-builder-pages";
import { OrderDetail } from "@/features/orders/components/order-detail";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockStockId } from "@/mocks/data/stock";
import { mockDb, resetMockDb } from "@/mocks/db";
import { warehouseChoice } from "@/mocks/handlers/stock";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

const push = vi.fn();
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  useRouter: () => ({ push, back: vi.fn(), replace: vi.fn() }),
}));

const RAJKOT = mockStockId(1, 2);

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

let keys = 0;
function key(): string {
  keys += 1;
  return `order-stock-test-${String(keys)}`;
}

function approvedOrder(): (typeof mockDb.orders)[number] {
  const order = mockDb.orders.find(
    (item) => item.status === "approved" && item.lines.some((line) => Number(line.qty_open) > 0),
  );
  if (order === undefined) throw new Error("No approved order with open lines");
  return order;
}

function reset(role: Role = "admin"): void {
  resetMockDb();
  signInAs(role);
}

describe("[DISP-003] Stock on orders (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("gives open lines their stock in the order's warehouse, for staff only", async () => {
    reset("admin");
    const order = approvedOrder();
    const read = await getOrder(order.id);
    const open = read.lines.filter((line) => Number(line.qtyOpen) > 0);
    expect(open.every((line) => line.stock !== null)).toBe(true);

    reset("dealer");
    const mine = mockDb.orders.find(
      (item) => item.partner?.id === "prt-201" && item.status !== "draft",
    );
    if (mine !== undefined) {
      const dealerView = await getOrder(mine.id);
      expect(dealerView.lines.every((line) => line.stock === null)).toBe(true);
    }
  });

  it("takes a dispatch's goods out of the warehouse it left from", async () => {
    reset("admin");
    const order = approvedOrder();
    const line = order.lines.find((item) => Number(item.qty_open) > 0);
    if (line === undefined) throw new Error("No open line");
    const before = mockDb.stockMovements.length;
    const dispatch = await createDispatch(order.id, {
      body: {
        dc_no: null,
        dc_date: null,
        invoice_no: null,
        invoice_date: null,
        dispatched_at: new Date().toISOString(),
        transporter: null,
        vehicle_no: null,
        lines: [{ order_line_id: line.id, qty: "1" }],
        warehouse_id: RAJKOT,
      },
      idempotencyKey: key(),
    });
    expect(dispatch.warehouse?.id).toBe(RAJKOT);
    expect(mockDb.stockMovements.length).toBe(before + 1);
    expect(mockDb.stockMovements[0]).toMatchObject({
      kind: "dispatch",
      qty: "-1",
      warehouse: { id: RAJKOT },
    });
  });

  it("refuses a warehouse from a dealer, and a switched-off one from staff", () => {
    reset("dealer");
    const fromDealer = warehouseChoice(RAJKOT);
    expect(fromDealer instanceof Response && fromDealer.status).toBe(422);
    reset("admin");
    const closed = warehouseChoice(mockStockId(1, 3));
    expect(closed instanceof Response && closed.status).toBe(422);
    expect(warehouseChoice(RAJKOT)).toMatchObject({ id: RAJKOT });
    expect(warehouseChoice(null)).toBeNull();
  });
});

describe("[DISP-003] Stock on order screens", () => {
  afterEach(() => {
    push.mockReset();
    reset();
  });

  it("offers Order to on a new order, defaulting to the default warehouse", async () => {
    reset("admin");
    renderWithProviders(
      <>
        <NewDirectOrder leadId={null} />
        <Toaster />
      </>,
    );
    await screen.findByRole("form", { name: "New order" });
    const field = await screen.findByLabelText("Order to");
    await waitFor(() => {
      expect(field).toHaveTextContent("Ahmedabad depot (default)");
    });
  });

  it("hides Order to from a dealer", async () => {
    reset("dealer");
    renderWithProviders(<NewDirectOrder leadId={null} />);
    await screen.findByRole("form", { name: "New order" });
    expect(screen.queryByLabelText("Order to")).toBeNull();
  });

  it("shows the stock under each open line, and Left from when recording a dispatch", async () => {
    reset("admin");
    const order = approvedOrder();
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <OrderDetail orderId={order.id} />
        <Toaster />
      </>,
    );
    expect((await screen.findAllByText(/available$/)).length).toBeGreaterThan(0);
    await user.click(await screen.findByRole("button", { name: /Record dispatch/ }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByLabelText("Left from")).toBeInTheDocument();
  });
});
