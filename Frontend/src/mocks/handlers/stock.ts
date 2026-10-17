import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { OrderWire } from "@/features/orders/api/orders.schemas";
import {
  MAX_AVAILABILITY_PRODUCTS,
  RECORDABLE_KINDS,
  type MovementWire,
  type StockRowWire,
  type WarehouseWire,
} from "@/features/stock/api/stock.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockStockId } from "@/mocks/data/stock";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * MSTR-014 … MSTR-016, DISP-003 · Stock (`docs/api/stock.md`). Every staff role reads; Dispatch
 * records (stock.create); Admin keeps the warehouses (stock.edit). Dealers get 403.
 */

type Action = "view" | "create" | "edit";

function allowed(action: Action): boolean {
  return can(mockPermissionsFor(readMockRole()), "stock", action);
}

function forbidden(): Response {
  return errorResponse(403, "forbidden", "Not in your permissions.");
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function fieldsOf(error: z.ZodError): Record<string, string> {
  return Object.fromEntries(
    error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
  );
}

/** Quantities in thousandths, so sums of decimals never drift. */
const milli = (value: string): number => Math.round(Number(value) * 1000);
const fromMilli = (value: number): string => {
  const text = (value / 1000).toFixed(3);
  return text.replace(/\.?0+$/, "") === "-0" ? "0" : text.replace(/\.?0+$/, "");
};

function defaultWarehouse(): WarehouseWire | undefined {
  return mockDb.warehouses.find((warehouse) => warehouse.is_default);
}

/** The warehouse an order's stock comes from: its own, else the default. */
export function orderWarehouseId(order: OrderWire): string | null {
  return order.warehouse?.id ?? defaultWarehouse()?.id ?? null;
}

const OPEN_STATUSES = new Set(["submitted", "approved", "partially_dispatched"]);

function onHand(warehouseId: string, productId: string): number {
  return mockDb.stockMovements
    .filter((row) => row.warehouse.id === warehouseId && row.product.id === productId)
    .reduce((sum, row) => sum + milli(row.qty), 0);
}

function committed(warehouseId: string, productId: string): number {
  return mockDb.orders
    .filter((order) => OPEN_STATUSES.has(order.status) && orderWarehouseId(order) === warehouseId)
    .flatMap((order) => order.lines)
    .filter((line) => line.product_id === productId)
    .reduce((sum, line) => sum + milli(line.qty_open), 0);
}

/** What a warehouse has left for a product, after open orders; negative is short. */
export function availableIn(warehouseId: string, productId: string): number {
  return onHand(warehouseId, productId) - committed(warehouseId, productId);
}

function stockRows(): StockRowWire[] {
  const pairs = new Map<
    string,
    { warehouse: MovementWire["warehouse"]; product: MovementWire["product"] }
  >();
  for (const row of mockDb.stockMovements) {
    pairs.set(`${row.warehouse.id}:${row.product.id}`, {
      warehouse: row.warehouse,
      product: row.product,
    });
  }
  return [...pairs.values()]
    .map(({ warehouse, product }): StockRowWire => {
      const have = onHand(warehouse.id, product.id);
      const owed = committed(warehouse.id, product.id);
      return {
        warehouse,
        product,
        on_hand: fromMilli(have),
        committed: fromMilli(owed),
        available: fromMilli(have - owed),
        uom: mockDb.products.find((item) => item.id === product.id)?.uom ?? "Nos",
      };
    })
    .sort(
      (left, right) =>
        left.warehouse.name.localeCompare(right.warehouse.name) ||
        left.product.name.localeCompare(right.product.name),
    );
}

/** Pages a list by an offset cursor, as the backend's `next_cursor: "100"`. */
function paged<T>(
  rows: readonly T[],
  url: URL,
): { data: T[]; meta: { limit: number; next_cursor: string | null } } {
  const limit = Math.min(100, Number(url.searchParams.get("limit") ?? "50") || 50);
  const start = Number(url.searchParams.get("cursor") ?? "0") || 0;
  const end = start + limit;
  return {
    data: rows.slice(start, end),
    meta: { limit, next_cursor: end < rows.length ? String(end) : null },
  };
}

const warehouseSchema = z.object({
  code: z.string().trim().min(1, "Give it a code.").max(20),
  name: z.string().trim().min(1, "Name it.").max(120),
  territory_id: z.string().min(1).nullish(),
  is_default: z.boolean().default(false),
  is_active: z.boolean().default(true),
});

const qty = z
  .union([z.number(), z.string()])
  .transform(String)
  .pipe(z.string().regex(/^-?\d+(\.\d{1,3})?$/, "A quantity, like 250 or 12.5."));

const movementSchema = z.object({
  warehouse_id: z.string().min(1),
  kind: z.enum(RECORDABLE_KINDS),
  reference: z.string().trim().max(120).nullish(),
  note: z.string().trim().max(500).nullish(),
  lines: z
    .array(z.object({ product_id: z.string().min(1), qty }))
    .min(1, "Add at least one product."),
});

function codeTaken(code: string, exceptId: string | null): boolean {
  const wanted = code.trim().toLowerCase();
  return mockDb.warehouses.some(
    (item) => item.id !== exceptId && item.code.toLowerCase() === wanted,
  );
}

export const stockHandlers = [
  http.get(buildApiUrl("/warehouses"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const all = new URL(request.url).searchParams.get("include_inactive") === "true";
    const rows = mockDb.warehouses
      .filter((warehouse) => all || warehouse.is_active)
      .sort(
        (left, right) =>
          Number(right.is_default) - Number(left.is_default) || left.name.localeCompare(right.name),
      );
    return HttpResponse.json({ data: rows });
  }),

  http.post(buildApiUrl("/warehouses"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return forbidden();
    const parsed = warehouseSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    if (codeTaken(body.code, null)) return errorResponse(409, "code_taken", "That code is taken.");
    if (body.is_default) {
      for (const item of mockDb.warehouses) item.is_default = false;
    }
    const warehouse: WarehouseWire = {
      id: mockStockId(1, 100 + mockDb.warehouses.length),
      code: body.code.toUpperCase(),
      name: body.name,
      territory_id: body.territory_id ?? null,
      is_default: body.is_default,
      is_active: body.is_active || body.is_default,
    };
    mockDb.warehouses.push(warehouse);
    return HttpResponse.json({ data: warehouse }, { status: 201 });
  }),

  http.patch(buildApiUrl("/warehouses/:warehouseId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("edit")) return forbidden();
    const warehouse = mockDb.warehouses.find((item) => item.id === params.warehouseId);
    if (warehouse === undefined) return errorResponse(404, "not_found", "No such warehouse.");
    const parsed = warehouseSchema.partial().safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    if (body.code !== undefined && codeTaken(body.code, warehouse.id)) {
      return errorResponse(409, "code_taken", "That code is taken.");
    }
    const leavingDefault =
      warehouse.is_default && (body.is_active === false || body.is_default === false);
    if (leavingDefault) {
      return errorResponse(
        409,
        "default_warehouse",
        "Make another warehouse the default before switching this one off.",
      );
    }
    if (body.is_default === true) {
      for (const item of mockDb.warehouses) item.is_default = false;
      warehouse.is_default = true;
      warehouse.is_active = true;
    }
    if (body.code !== undefined) warehouse.code = body.code.toUpperCase();
    if (body.name !== undefined) warehouse.name = body.name;
    if (body.territory_id !== undefined) warehouse.territory_id = body.territory_id ?? null;
    if (body.is_active !== undefined && !warehouse.is_default) warehouse.is_active = body.is_active;
    return HttpResponse.json({ data: warehouse });
  }),

  http.get(buildApiUrl("/stock"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const url = new URL(request.url);
    const warehouseId = url.searchParams.get("warehouse_id");
    const productId = url.searchParams.get("product_id");
    const shortOnly = url.searchParams.get("short_only") === "true";
    const rows = stockRows()
      .filter((row) => warehouseId === null || row.warehouse.id === warehouseId)
      .filter((row) => productId === null || row.product.id === productId)
      .filter((row) => !shortOnly || milli(row.available) < 0);
    return HttpResponse.json(paged(rows, url));
  }),

  http.get(buildApiUrl("/stock/availability"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const url = new URL(request.url);
    const warehouseId = url.searchParams.get("warehouse_id") ?? defaultWarehouse()?.id ?? "";
    if (!mockDb.warehouses.some((item) => item.id === warehouseId)) {
      return errorResponse(404, "not_found", "No such warehouse.");
    }
    const productIds = (url.searchParams.get("product_ids") ?? "").split(",").filter(Boolean);
    if (productIds.length > MAX_AVAILABILITY_PRODUCTS) {
      return invalid({ product_ids: `At most ${String(MAX_AVAILABILITY_PRODUCTS)}.` });
    }
    return HttpResponse.json({
      data: {
        warehouse_id: warehouseId,
        items: productIds.map((productId) => ({
          product_id: productId,
          available: fromMilli(availableIn(warehouseId, productId)),
          on_hand: fromMilli(onHand(warehouseId, productId)),
        })),
      },
    });
  }),

  http.get(buildApiUrl("/stock/movements"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("view")) return forbidden();
    const url = new URL(request.url);
    const warehouseId = url.searchParams.get("warehouse_id");
    const productId = url.searchParams.get("product_id");
    const rows = mockDb.stockMovements
      .filter((row) => warehouseId === null || row.warehouse.id === warehouseId)
      .filter((row) => productId === null || row.product.id === productId);
    return HttpResponse.json(paged(rows, url));
  }),

  http.post(buildApiUrl("/stock/movements"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!allowed("create")) return forbidden();
    const parsed = movementSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    const warehouse = mockDb.warehouses.find((item) => item.id === body.warehouse_id);
    if (warehouse === undefined) return errorResponse(404, "not_found", "No such warehouse.");
    if (!warehouse.is_active) {
      return errorResponse(409, "warehouse_inactive", "That warehouse is switched off.");
    }
    const fields: Record<string, string> = {};
    body.lines.forEach((line, index) => {
      if (body.kind === "receipt" && milli(line.qty) <= 0) {
        fields[`lines.${String(index)}.qty`] = "A receipt adds stock: more than 0.";
      }
      if (body.kind === "adjustment" && milli(line.qty) === 0) {
        fields[`lines.${String(index)}.qty`] = "Not 0.";
      }
      const product = mockDb.products.find((item) => item.id === line.product_id);
      if (
        product !== undefined &&
        product.uom_decimals === 0 &&
        !Number.isInteger(Number(line.qty))
      ) {
        fields[`lines.${String(index)}.qty`] = "This product is counted in whole units.";
      }
    });
    if (Object.keys(fields).length > 0) {
      const precision = Object.values(fields).some((reason) => reason.includes("whole units"));
      return errorResponse(
        422,
        precision ? "qty_precision" : "validation_error",
        "Some quantities need correcting.",
        fields,
      );
    }
    for (const line of body.lines) {
      const product = mockDb.products.find((item) => item.id === line.product_id);
      if (product === undefined || !product.is_active) {
        return errorResponse(409, "product_inactive", "A product is switched off.");
      }
      if (onHand(warehouse.id, product.id) + milli(line.qty) < 0) {
        return errorResponse(409, "negative_stock", "That would take stock below zero.");
      }
    }
    const now = new Date().toISOString();
    const created = body.lines.map((line) => {
      const product = mockDb.products.find((item) => item.id === line.product_id);
      const row: MovementWire = {
        id: mockStockId(2, 1000 + mockDb.stockMovements.length),
        warehouse: { id: warehouse.id, code: warehouse.code, name: warehouse.name },
        product: {
          id: line.product_id,
          code: product?.item_code ?? null,
          name: product?.description ?? "",
        },
        qty: line.qty,
        kind: body.kind,
        reference: body.reference?.trim() ? body.reference.trim() : null,
        note: body.note?.trim() ? body.note.trim() : null,
        dispatch_no: null,
        order: null,
        created_by: { id: "usr-001", full_name: "Aarav Desai" },
        created_at: now,
      };
      mockDb.stockMovements.unshift(row);
      return {
        id: row.id,
        product_id: line.product_id,
        qty: line.qty,
        on_hand_after: fromMilli(onHand(warehouse.id, line.product_id)),
      };
    });
    return HttpResponse.json({ data: { movements: created } }, { status: 201 });
  }),
];
