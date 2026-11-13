import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { Toaster } from "@/components/ui/sonner";
import {
  createWarehouse,
  getAvailability,
  listStock,
  patchWarehouse,
  recordStock,
} from "@/features/stock/api/stock.api";
import { quantityText, signedQuantity } from "@/features/stock/lib/stock-labels";
import { isApiError } from "@/lib/api/errors";
import { buildApiUrl } from "@/lib/api/url";
import type { Role } from "@/lib/auth/roles";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { mockMeFor } from "@/mocks/data/sessions";
import { mockStockId } from "@/mocks/data/stock";
import { mockDb, resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";
import { renderWithProviders } from "@/test/render";

import { StockPage } from "./stock-page";

function signInAs(role: Role): void {
  writeMockRole(role);
  server.use(http.get(buildApiUrl("/auth/me"), () => HttpResponse.json(mockMeFor(role))));
}

async function failureOf(
  call: Promise<unknown>,
): Promise<{ status: number | undefined; code: string | undefined }> {
  const error = await call.then(
    () => null,
    (caught: unknown) => caught,
  );
  return isApiError(error)
    ? { status: error.status, code: error.code }
    : { status: undefined, code: undefined };
}

let keys = 0;
function key(): string {
  keys += 1;
  return `stock-test-${String(keys)}`;
}

const AHMEDABAD = mockStockId(1, 1);
const RAJKOT = mockStockId(1, 2);
const CLOSED = mockStockId(1, 3);

function firstStockedProduct(): string {
  const row = mockDb.stockMovements.find((item) => item.warehouse.id === AHMEDABAD);
  if (row === undefined) throw new Error("No stock seeded");
  return row.product.id;
}

function reset(role: Role = "dispatch_manager"): void {
  resetMockDb();
  signInAs(role);
}

describe("[MSTR-014] Stock (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("works out available as on hand less committed, and keeps it from dealers", async () => {
    reset("employee");
    const page = await listStock({
      warehouseId: AHMEDABAD,
      productId: null,
      shortOnly: false,
      cursor: null,
    });
    expect(page.items.length).toBeGreaterThan(0);
    for (const row of page.items) {
      expect(Number(row.available)).toBeCloseTo(Number(row.onHand) - Number(row.committed));
    }
    reset("dealer");
    expect(
      (
        await failureOf(
          listStock({ warehouseId: null, productId: null, shortOnly: false, cursor: null }),
        )
      ).status,
    ).toBe(403);
  });

  it("answers availability for an order's products", async () => {
    reset("employee");
    const product = firstStockedProduct();
    const availability = await getAvailability(AHMEDABAD, [product]);
    expect(availability.items[0]?.productId).toBe(product);
    expect(Number(availability.items[0]?.onHand)).toBeGreaterThan(0);
  });
});

describe("[MSTR-015] Recording stock (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("records a receipt, and refuses a correction below zero or a closed warehouse", async () => {
    reset("dispatch_manager");
    const product = firstStockedProduct();
    const before = await getAvailability(AHMEDABAD, [product]);
    const saved = await recordStock({
      body: {
        warehouse_id: AHMEDABAD,
        kind: "receipt",
        reference: "GRN 1",
        note: null,
        lines: [{ product_id: product, qty: "10" }],
      },
      idempotencyKey: key(),
    });
    expect(Number(saved[0]?.onHandAfter)).toBe(Number(before.items[0]?.onHand) + 10);
    expect(
      (
        await failureOf(
          recordStock({
            body: {
              warehouse_id: AHMEDABAD,
              kind: "adjustment",
              reference: null,
              note: null,
              lines: [{ product_id: product, qty: "-999999" }],
            },
            idempotencyKey: key(),
          }),
        )
      ).code,
    ).toBe("negative_stock");
    expect(
      (
        await failureOf(
          recordStock({
            body: {
              warehouse_id: CLOSED,
              kind: "receipt",
              reference: null,
              note: null,
              lines: [{ product_id: product, qty: "1" }],
            },
            idempotencyKey: key(),
          }),
        )
      ).code,
    ).toBe("warehouse_inactive");
  });

  it("lets only Dispatch and Admin record", async () => {
    reset("employee");
    expect(
      (
        await failureOf(
          recordStock({
            body: {
              warehouse_id: AHMEDABAD,
              kind: "receipt",
              reference: null,
              note: null,
              lines: [{ product_id: firstStockedProduct(), qty: "1" }],
            },
            idempotencyKey: key(),
          }),
        )
      ).status,
    ).toBe(403);
  });
});

describe("[MSTR-016] Warehouses (contract)", () => {
  afterEach(() => {
    reset();
  });

  it("refuses a taken code, and switching off the default", async () => {
    reset("admin");
    const body = {
      code: "ahd-1",
      name: "Another",
      territory_id: null,
      is_default: false,
      is_active: true,
    };
    expect((await failureOf(createWarehouse({ body, idempotencyKey: key() }))).code).toBe(
      "code_taken",
    );
    expect(
      (
        await failureOf(
          patchWarehouse(AHMEDABAD, { body: { is_active: false }, idempotencyKey: key() }),
        )
      ).code,
    ).toBe("default_warehouse");
    const moved = await patchWarehouse(RAJKOT, {
      body: { is_default: true },
      idempotencyKey: key(),
    });
    expect(moved.isDefault).toBe(true);
    expect(mockDb.warehouses.find((item) => item.id === AHMEDABAD)?.is_default).toBe(false);
  });
});

describe("[MSTR-014] Stock labels", () => {
  it("writes quantities with their unit and sign", () => {
    expect(quantityText("1250", "m")).toBe("1,250 m");
    expect(quantityText("12.5")).toBe("12.5");
    expect(signedQuantity("250")).toBe("+250");
    expect(signedQuantity("-25")).toBe("−25");
  });
});

describe("[MSTR-014] StockPage", () => {
  afterEach(() => {
    reset();
  });

  function show(searchParams = ""): ReturnType<typeof userEvent.setup> {
    const user = userEvent.setup();
    renderWithProviders(
      <>
        <StockPage />
        <Toaster />
      </>,
      { searchParams },
    );
    return user;
  }

  it("shows stock by warehouse and product, without recording for a reader", async () => {
    reset("employee");
    show();
    const table = await screen.findByRole("table");
    expect(within(table).getAllByText("Ahmedabad depot").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Record stock" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Warehouses" })).toBeNull();
  });

  it("records stock received, asking for a quantity first", async () => {
    reset("dispatch_manager");
    const user = show();
    await screen.findByRole("table");
    await user.click(screen.getByRole("button", { name: "Record stock" }));
    const form = await screen.findByRole("form", { name: "Record stock" });
    await user.click(within(form).getByRole("button", { name: "Record" }));
    expect(await within(form).findByText("Add at least one product.")).toBeInTheDocument();

    const product = mockDb.products.find((item) => item.id === firstStockedProduct());
    if (product === undefined) throw new Error("No product");
    await user.type(within(form).getByLabelText("Add a product"), product.description.slice(0, 6));
    await user.click(
      await screen.findByRole("option", { name: new RegExp(product.description.slice(0, 6)) }),
    );
    await user.click(within(form).getByRole("button", { name: "Record" }));
    expect(await within(form).findByText("Enter how many.")).toBeInTheDocument();
    await user.type(within(form).getByLabelText(product.description), "40");
    await user.click(
      await within(form).findByRole("button", { name: "Record" }, { timeout: 4000 }),
    );
    expect(await screen.findByText("Stock received recorded")).toBeInTheDocument();
  });

  it("lists the ledger, and lets Admin keep the warehouses", async () => {
    reset("admin");
    const user = show("?tab=ledger");
    const ledger = await screen.findByRole("list", { name: "Stock movements" });
    expect(within(ledger).getAllByText("Received").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Warehouses" }));
    const list = await screen.findByRole("list", { name: "Warehouses" });
    expect(within(list).getAllByText("Default").length).toBeGreaterThan(0);
    await user.click(within(list).getByRole("button", { name: "Make Rajkot depot the default" }));
    expect(await screen.findByText("Rajkot depot is now the default")).toBeInTheDocument();
  });
});
