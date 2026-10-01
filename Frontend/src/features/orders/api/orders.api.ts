import {
  TIMELINE_PAGE_SIZE,
  timelinePageSchema,
  type TimelinePage,
} from "@/features/leads/api/leads.schemas";
import { pdfLinkResponseSchema, type PdfLink } from "@/features/quotations/api/quotations.schemas";
import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  dispatchResponseSchema,
  noContentSchema,
  orderPageSchema,
  orderResponseSchema,
  type CreateDispatchRequest,
  type CreateOrderFromQuotations,
  type Dispatch,
  type ExpectedStatusRequest,
  type Order,
  type OrderListParams,
  type OrderPage,
  type PatchOrderRequest,
  type RemarkRequest,
} from "./orders.schemas";

const log = createLogger({ file: "features/orders/api/orders.api.ts", dataId: "SO-001" });

/** A write's body and the key that makes a retry of it safe; a new key after a refusal. */
export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

/** SO-001 · GET /orders — one page, newest first, with the matching total. */
export async function listOrders(
  params: OrderListParams,
  signal?: AbortSignal,
): Promise<OrderPage> {
  const page = await apiRequest({
    dataId: "SO-001",
    logger: log,
    fn: "listOrders",
    path: "/orders",
    query: {
      limit: params.pageSize,
      cursor: params.cursor,
      include_total: true,
      q: params.q,
      status: params.status.join(","),
      order_type: params.orderType,
      owner: params.mine ? "me" : undefined,
      lead_id: params.leadId,
    },
    schema: orderPageSchema,
    signal,
  });
  if (page.skipped > 0) {
    // A backend-side issue: the page is still shown, so it would otherwise go unnoticed.
    log.warn(
      "listOrders",
      `left out ${String(page.skipped)} order(s) that did not match the contract`,
      {
        dataId: "SO-001",
        context: { skipped: page.skipped, kept: page.items.length },
      },
    );
  }
  return page;
}

/** SO-002 · GET /orders/{id}. */
export function getOrder(orderId: string, signal?: AbortSignal): Promise<Order> {
  return apiRequest({
    dataId: "SO-002",
    logger: log,
    fn: "getOrder",
    path: `/orders/${encodeURIComponent(orderId)}`,
    schema: orderResponseSchema,
    signal,
  });
}

/** SO-002 · GET /orders/{id}/pdf — a ten-minute link, asked for on the click. */
export function getOrderPdf(orderId: string): Promise<PdfLink> {
  return apiRequest({
    dataId: "SO-002",
    logger: log,
    fn: "getOrderPdf",
    path: `/orders/${encodeURIComponent(orderId)}/pdf`,
    schema: pdfLinkResponseSchema,
  });
}

/** SO-002 · GET /orders/{id}/timeline — newest first, a page at a time. */
export async function getOrderTimeline(
  { orderId, cursor }: { orderId: string; cursor: string | null },
  signal?: AbortSignal,
): Promise<TimelinePage> {
  const page = await apiRequest({
    dataId: "SO-002",
    logger: log,
    fn: "getOrderTimeline",
    path: `/orders/${encodeURIComponent(orderId)}/timeline`,
    query: { limit: TIMELINE_PAGE_SIZE, cursor },
    schema: timelinePageSchema,
    signal,
  });
  if (page.skipped > 0) {
    log.warn("getOrderTimeline", `left out ${String(page.skipped)} event(s)`, {
      dataId: "SO-002",
      context: { skipped: page.skipped },
    });
  }
  return page;
}

/** SO-003 · POST /orders from accepted quotations; 201 with a draft that has no number. */
export function createOrder({
  body,
  idempotencyKey,
}: WriteInput<CreateOrderFromQuotations>): Promise<Order> {
  return apiRequest({
    dataId: "SO-003",
    logger: log,
    fn: "createOrder",
    method: "POST",
    path: "/orders",
    body,
    idempotencyKey,
    schema: orderResponseSchema,
  });
}

/** SO-003 · PATCH /orders/{id} — a draft's header. */
export function patchOrder(
  orderId: string,
  { body, idempotencyKey }: WriteInput<PatchOrderRequest>,
): Promise<Order> {
  return apiRequest({
    dataId: "SO-003",
    logger: log,
    fn: "patchOrder",
    method: "PATCH",
    path: `/orders/${encodeURIComponent(orderId)}`,
    body,
    idempotencyKey,
    schema: orderResponseSchema,
  });
}

/** SO-003 · DELETE /orders/{id} — a draft never submitted; a numbered one is cancelled instead. */
export async function deleteOrder(orderId: string, idempotencyKey: string): Promise<void> {
  await apiRequest({
    dataId: "SO-003",
    logger: log,
    fn: "deleteOrder",
    method: "DELETE",
    path: `/orders/${encodeURIComponent(orderId)}`,
    idempotencyKey,
    schema: noContentSchema,
  });
}

/** SO-004 · POST /orders/{id}/submit — numbers the order and builds the approval chain. */
export function submitOrder(
  orderId: string,
  { body, idempotencyKey }: WriteInput<ExpectedStatusRequest>,
): Promise<Order> {
  return apiRequest({
    dataId: "SO-004",
    logger: log,
    fn: "submitOrder",
    method: "POST",
    path: `/orders/${encodeURIComponent(orderId)}/submit`,
    body,
    idempotencyKey,
    schema: orderResponseSchema,
  });
}

/** SO-004 · POST /orders/{id}/cancel — with a reason. */
export function cancelOrder(
  orderId: string,
  { body, idempotencyKey }: WriteInput<RemarkRequest>,
): Promise<Order> {
  return apiRequest({
    dataId: "SO-004",
    logger: log,
    fn: "cancelOrder",
    method: "POST",
    path: `/orders/${encodeURIComponent(orderId)}/cancel`,
    body,
    idempotencyKey,
    schema: orderResponseSchema,
  });
}

/** DISP-002 · POST /orders/{id}/dispatches — 201 with the dispatch. */
export function createDispatch(
  orderId: string,
  { body, idempotencyKey }: WriteInput<CreateDispatchRequest>,
): Promise<Dispatch> {
  return apiRequest({
    dataId: "DISP-002",
    logger: log,
    fn: "createDispatch",
    method: "POST",
    path: `/orders/${encodeURIComponent(orderId)}/dispatches`,
    body,
    idempotencyKey,
    schema: dispatchResponseSchema,
  });
}

/**
 * DISP-002 · POST /dispatches/{id}/void — the dispatch stays on record, marked void; its
 * quantities are open again. Answers with the order.
 */
export function voidDispatch(
  dispatchId: string,
  { body, idempotencyKey }: WriteInput<RemarkRequest>,
): Promise<Order> {
  return apiRequest({
    dataId: "DISP-002",
    logger: log,
    fn: "voidDispatch",
    method: "POST",
    path: `/dispatches/${encodeURIComponent(dispatchId)}/void`,
    body,
    idempotencyKey,
    schema: orderResponseSchema,
  });
}

/** DISP-002 · POST /orders/{id}/close-short — every open quantity becomes short. */
export function closeOrderShort(
  orderId: string,
  { body, idempotencyKey }: WriteInput<RemarkRequest>,
): Promise<Order> {
  return apiRequest({
    dataId: "DISP-002",
    logger: log,
    fn: "closeOrderShort",
    method: "POST",
    path: `/orders/${encodeURIComponent(orderId)}/close-short`,
    body,
    idempotencyKey,
    schema: orderResponseSchema,
  });
}
