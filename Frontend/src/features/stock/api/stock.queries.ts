import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import { listMovements, listStock, listWarehouses } from "./stock.api";
import type { MovementListParams, StockListParams } from "./stock.schemas";

/**
 * Query keys for stock. Invalidate by prefix:
 *   stockKeys.all → warehouses, the stock list, the ledger and availability
 */
export const stockKeys = {
  all: ["stock"] as const,
  warehouses: (includeInactive: boolean) =>
    [...stockKeys.all, "warehouses", includeInactive] as const,
  list: (params: StockListParams) => [...stockKeys.all, "list", params] as const,
  movements: (params: MovementListParams) => [...stockKeys.all, "movements", params] as const,
  availability: (warehouseId: string, productIds: readonly string[]) =>
    [...stockKeys.all, "availability", warehouseId, productIds] as const,
};

const FIRST_PAGE: string | null = null;

/** MSTR-016, DISP-003 · Warehouses, the default first. */
export function warehousesQueryOptions(includeInactive = false) {
  return queryOptions({
    queryKey: stockKeys.warehouses(includeInactive),
    queryFn: ({ signal }) => listWarehouses(includeInactive, signal),
    staleTime: 5 * 60_000,
    meta: { dataId: "MSTR-016" },
  });
}

/** MSTR-014 · The stock list, page by page. */
export function stockListQueryOptions(params: StockListParams) {
  return infiniteQueryOptions({
    queryKey: stockKeys.list(params),
    queryFn: ({ pageParam, signal }) => listStock({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (page) => page.nextCursor,
    placeholderData: keepPreviousData,
    meta: { dataId: "MSTR-014" },
  });
}

/** MSTR-014 · The ledger, page by page. */
export function movementsQueryOptions(params: MovementListParams) {
  return infiniteQueryOptions({
    queryKey: stockKeys.movements(params),
    queryFn: ({ pageParam, signal }) => listMovements({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (page) => page.nextCursor,
    placeholderData: keepPreviousData,
    meta: { dataId: "MSTR-014" },
  });
}
