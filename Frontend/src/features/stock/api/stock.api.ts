import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  availabilitySchema,
  movementPageSchema,
  recordedSchema,
  stockPageSchema,
  warehouseListSchema,
  warehouseResponseSchema,
  type Availability,
  type MovementListParams,
  type MovementPage,
  type RecordStockRequest,
  type Recorded,
  type StockListParams,
  type StockPage,
  type Warehouse,
  type WarehouseRequest,
} from "./stock.schemas";

const log = createLogger({ file: "features/stock/api/stock.api.ts", dataId: "MSTR-014" });

export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

const PAGE_SIZE = 50;

/** MSTR-016, DISP-003 · Warehouses, the default first; switched-off ones on request. */
export function listWarehouses(
  includeInactive: boolean,
  signal?: AbortSignal,
): Promise<Warehouse[]> {
  return apiRequest({
    dataId: "MSTR-016",
    logger: log,
    fn: "listWarehouses",
    path: "/warehouses",
    query: { include_inactive: includeInactive ? "true" : undefined },
    schema: warehouseListSchema,
    signal,
  });
}

/** MSTR-016 · Add a warehouse (stock.edit). 409 code_taken, ignoring case. */
export function createWarehouse({
  body,
  idempotencyKey,
}: WriteInput<WarehouseRequest>): Promise<Warehouse> {
  return apiRequest({
    dataId: "MSTR-016",
    logger: log,
    fn: "createWarehouse",
    method: "POST",
    path: "/warehouses",
    body,
    idempotencyKey,
    schema: warehouseResponseSchema,
  });
}

/**
 * MSTR-016 · Change a warehouse; `is_default: true` moves the default. 409 default_warehouse:
 * make another the default before switching this one off.
 */
export function patchWarehouse(
  warehouseId: string,
  { body, idempotencyKey }: WriteInput<Partial<WarehouseRequest>>,
): Promise<Warehouse> {
  return apiRequest({
    dataId: "MSTR-016",
    logger: log,
    fn: "patchWarehouse",
    method: "PATCH",
    path: `/warehouses/${encodeURIComponent(warehouseId)}`,
    body,
    idempotencyKey,
    schema: warehouseResponseSchema,
  });
}

/** MSTR-014 · Stock by warehouse and product: on hand, committed, available. */
export function listStock(
  params: StockListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<StockPage> {
  return apiRequest({
    dataId: "MSTR-014",
    logger: log,
    fn: "listStock",
    path: "/stock",
    query: {
      warehouse_id: params.warehouseId ?? undefined,
      product_id: params.productId ?? undefined,
      short_only: params.shortOnly ? "true" : undefined,
      limit: PAGE_SIZE,
      cursor: params.cursor ?? undefined,
    },
    schema: stockPageSchema,
    signal,
  });
}

/** MSTR-014 · The stock ledger, newest first, with the dispatch and order behind each. */
export function listMovements(
  params: MovementListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<MovementPage> {
  return apiRequest({
    dataId: "MSTR-014",
    logger: log,
    fn: "listMovements",
    path: "/stock/movements",
    query: {
      warehouse_id: params.warehouseId ?? undefined,
      product_id: params.productId ?? undefined,
      limit: PAGE_SIZE,
      cursor: params.cursor ?? undefined,
    },
    schema: movementPageSchema,
    signal,
  });
}

/**
 * MSTR-015 · Record stock received, or a correction (stock.create). 409 negative_stock,
 * warehouse_inactive, product_inactive; 422 qty_precision.
 */
export function recordStock({
  body,
  idempotencyKey,
}: WriteInput<RecordStockRequest>): Promise<Recorded> {
  return apiRequest({
    dataId: "MSTR-015",
    logger: log,
    fn: "recordStock",
    method: "POST",
    path: "/stock/movements",
    body,
    idempotencyKey,
    schema: recordedSchema,
  });
}

/** DISP-003 · What a warehouse has available for these products (up to 100). */
export function getAvailability(
  warehouseId: string,
  productIds: readonly string[],
  signal?: AbortSignal,
): Promise<Availability> {
  return apiRequest({
    dataId: "DISP-003",
    logger: log,
    fn: "getAvailability",
    path: "/stock/availability",
    query: { warehouse_id: warehouseId, product_ids: productIds.join(",") },
    schema: availabilitySchema,
    signal,
  });
}
