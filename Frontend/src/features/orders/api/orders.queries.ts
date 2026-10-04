import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getOrder, getOrderTimeline, listDispatches, listOrders } from "./orders.api";
import {
  DEFAULT_ORDER_PAGE_SIZE,
  type DispatchListParams,
  type OrderListParams,
} from "./orders.schemas";

/** How often an order is re-read while its PDF renders (a few seconds). */
export const ORDER_PDF_POLL_MS = 3000;
/** How often a submitted order is re-read while its approval chain moves. */
export const ORDER_APPROVAL_POLL_MS = 60_000;

/**
 * Query keys for orders. Invalidate by prefix:
 *   orderKeys.all      → everything about orders
 *   orderKeys.lists()  → every list, whatever the filters
 */
export const orderKeys = {
  all: ["orders"] as const,
  lists: () => [...orderKeys.all, "list"] as const,
  list: (params: OrderListParams) => [...orderKeys.lists(), params] as const,
  details: () => [...orderKeys.all, "detail"] as const,
  detail: (orderId: string) => [...orderKeys.details(), orderId] as const,
  timelines: () => [...orderKeys.all, "timeline"] as const,
  timeline: (orderId: string) => [...orderKeys.timelines(), orderId] as const,
  // Under lists(), so recording or voiding a dispatch refreshes the queue as well.
  toShip: () => [...orderKeys.lists(), "to-ship"] as const,
  dispatches: (params: DispatchListParams) => [...orderKeys.lists(), "dispatches", params] as const,
};

const FIRST_PAGE: string | null = null;

/** Orders waiting to ship: approved, or partly sent. */
const TO_SHIP: OrderListParams = {
  cursor: null,
  pageSize: DEFAULT_ORDER_PAGE_SIZE,
  q: "",
  status: ["approved", "partially_dispatched"],
  orderType: null,
  mine: false,
  leadId: null,
  quotationId: null,
};

/** DISP-001 · The orders waiting to ship, a page at a time. */
export function ordersToShipQueryOptions() {
  return infiniteQueryOptions({
    queryKey: orderKeys.toShip(),
    queryFn: ({ pageParam, signal }) => listOrders({ ...TO_SHIP, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "DISP-001" },
  });
}

/** DISP-001 · The dispatch log, newest first, a page at a time. */
export function dispatchListQueryOptions(params: DispatchListParams) {
  return infiniteQueryOptions({
    queryKey: orderKeys.dispatches(params),
    queryFn: ({ pageParam, signal }) => listDispatches({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "DISP-001" },
  });
}

/** SO-001 · Keeps the previous page on screen while the next one loads. */
export function orderListQueryOptions(params: OrderListParams) {
  return queryOptions({
    queryKey: orderKeys.list(params),
    queryFn: ({ signal }) => listOrders(params, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "SO-001" },
  });
}

/**
 * SO-002 · Re-reads every few seconds while the approved order's PDF renders, and now and then
 * while it waits for approval; stops otherwise.
 */
export function orderDetailQueryOptions(orderId: string) {
  return queryOptions({
    queryKey: orderKeys.detail(orderId),
    queryFn: ({ signal }) => getOrder(orderId, signal),
    refetchInterval: (query) => {
      const order = query.state.data;
      if (order?.pdfState === "pending") return ORDER_PDF_POLL_MS;
      if (order?.status === "submitted") return ORDER_APPROVAL_POLL_MS;
      return false;
    },
    meta: { dataId: "SO-002" },
  });
}

const NEWEST_TIMELINE_PAGE: string | null = null;

/** SO-002 · The order's history, newest first, a page at a time. */
export function orderTimelineQueryOptions(orderId: string) {
  return infiniteQueryOptions({
    queryKey: orderKeys.timeline(orderId),
    queryFn: ({ pageParam, signal }) => getOrderTimeline({ orderId, cursor: pageParam }, signal),
    initialPageParam: NEWEST_TIMELINE_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "SO-002" },
  });
}
