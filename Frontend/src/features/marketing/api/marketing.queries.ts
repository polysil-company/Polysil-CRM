import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getMarketingOrder, listMarketingOrders, listMaterials } from "./marketing.api";
import type { MarketingOrderListParams } from "./marketing.schemas";

/**
 * Query keys for marketing material. Invalidate by prefix:
 *   marketingKeys.all      → everything
 *   marketingKeys.orders() → every order list and order
 */
export const marketingKeys = {
  all: ["marketing"] as const,
  materials: (activeOnly: boolean) => [...marketingKeys.all, "materials", activeOnly] as const,
  orders: () => [...marketingKeys.all, "orders"] as const,
  orderList: (params: MarketingOrderListParams) =>
    [...marketingKeys.orders(), "list", params] as const,
  order: (orderId: string) => [...marketingKeys.orders(), "one", orderId] as const,
};

const FIRST_PAGE: string | null = null;

/** MKT-002 · The catalogue. */
export function materialsQueryOptions(activeOnly: boolean) {
  return queryOptions({
    queryKey: marketingKeys.materials(activeOnly),
    queryFn: ({ signal }) => listMaterials(activeOnly, signal),
    meta: { dataId: "MKT-002" },
  });
}

/** MKT-003 · A view of the orders, page by page. */
export function marketingOrderListQueryOptions(params: MarketingOrderListParams) {
  return infiniteQueryOptions({
    queryKey: marketingKeys.orderList(params),
    queryFn: ({ pageParam, signal }) =>
      listMarketingOrders({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (page) => page.nextCursor,
    placeholderData: keepPreviousData,
    meta: { dataId: "MKT-003" },
  });
}

/** MKT-003 · One order. */
export function marketingOrderQueryOptions(orderId: string) {
  return queryOptions({
    queryKey: marketingKeys.order(orderId),
    queryFn: ({ signal }) => getMarketingOrder(orderId, signal),
    meta: { dataId: "MKT-003" },
  });
}
