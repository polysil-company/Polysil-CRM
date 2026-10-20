import { apiDownload, apiRequest, type DownloadedFile } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  marketingOrderPageSchema,
  marketingOrderResponseSchema,
  materialListSchema,
  materialResponseSchema,
  type DispatchRequest,
  type MarketingAction,
  type MarketingOrder,
  type MarketingOrderCreateRequest,
  type MarketingOrderListParams,
  type MarketingOrderPage,
  type Material,
  type MaterialCreateRequest,
  type MaterialPatchRequest,
} from "./marketing.schemas";

const log = createLogger({ file: "features/marketing/api/marketing.api.ts", dataId: "MKT-003" });

export interface WriteInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

/** The list's view as the backend's filters. */
function viewQuery(params: MarketingOrderListParams): Record<string, string | undefined> {
  switch (params.view) {
    case "mine":
      return { mine: "true" };
    case "awaiting":
      return { awaiting: "me" };
    case "dispatch":
      return { status: "approved" };
    case "all":
      return {};
  }
}

/** MKT-002 · The catalogue with today's price and company share; `active` narrows it. */
export function listMaterials(activeOnly: boolean, signal?: AbortSignal): Promise<Material[]> {
  return apiRequest({
    dataId: "MKT-002",
    logger: log,
    fn: "listMaterials",
    path: "/marketing-materials",
    query: { active: activeOnly ? "true" : undefined },
    schema: materialListSchema,
    signal,
  });
}

/** MKT-002 · Add an item with its price from today (marketing_material.edit). 409 code_taken. */
export function createMaterial({
  body,
  idempotencyKey,
}: WriteInput<MaterialCreateRequest>): Promise<Material> {
  return apiRequest({
    dataId: "MKT-002",
    logger: log,
    fn: "createMaterial",
    method: "POST",
    path: "/marketing-materials",
    body,
    idempotencyKey,
    schema: materialResponseSchema,
  });
}

/** MKT-002 · Change an item; a new price starts today, once a day (409 price_changed_today). */
export function patchMaterial(
  materialId: string,
  { body, idempotencyKey }: WriteInput<MaterialPatchRequest>,
): Promise<Material> {
  return apiRequest({
    dataId: "MKT-002",
    logger: log,
    fn: "patchMaterial",
    method: "PATCH",
    path: `/marketing-materials/${encodeURIComponent(materialId)}`,
    body,
    idempotencyKey,
    schema: materialResponseSchema,
  });
}

/** MKT-003 · Marketing orders in scope, newest first. */
export function listMarketingOrders(
  params: MarketingOrderListParams & { cursor: string | null },
  signal?: AbortSignal,
): Promise<MarketingOrderPage> {
  return apiRequest({
    dataId: "MKT-003",
    logger: log,
    fn: "listMarketingOrders",
    path: "/marketing-orders",
    query: { ...viewQuery(params), cursor: params.cursor ?? undefined },
    schema: marketingOrderPageSchema,
    signal,
  });
}

/** MKT-003 · The same list as an Excel file. */
export function exportMarketingOrders(params: MarketingOrderListParams): Promise<DownloadedFile> {
  return apiDownload({
    dataId: "MKT-003",
    logger: log,
    fn: "exportMarketingOrders",
    path: "/marketing-orders/export",
    query: viewQuery(params),
  });
}

/** MKT-003 · One order with its lines, decision, dispatch and `can`. */
export function getMarketingOrder(orderId: string, signal?: AbortSignal): Promise<MarketingOrder> {
  return apiRequest({
    dataId: "MKT-003",
    logger: log,
    fn: "getMarketingOrder",
    path: `/marketing-orders/${encodeURIComponent(orderId)}`,
    schema: marketingOrderResponseSchema,
    signal,
  });
}

/** MKT-003 · Order material; it goes straight to the District Manager. 422 material_inactive. */
export function createMarketingOrder({
  body,
  idempotencyKey,
}: WriteInput<MarketingOrderCreateRequest>): Promise<MarketingOrder> {
  return apiRequest({
    dataId: "MKT-003",
    logger: log,
    fn: "createMarketingOrder",
    method: "POST",
    path: "/marketing-orders",
    body,
    idempotencyKey,
    schema: marketingOrderResponseSchema,
  });
}

/**
 * MKT-004 · Approve, reject (a remark is required) or cancel (a remark once approved).
 * 403 own_order or not_your_approval; 409 status_changed; 422 remark_required.
 */
export function actOnMarketingOrder(
  orderId: string,
  action: MarketingAction,
  { body, idempotencyKey }: WriteInput<{ readonly remark: string | null }>,
): Promise<MarketingOrder> {
  return apiRequest({
    dataId: "MKT-004",
    logger: log,
    fn: "actOnMarketingOrder",
    method: "POST",
    path: `/marketing-orders/${encodeURIComponent(orderId)}/${action}`,
    body,
    idempotencyKey,
    schema: marketingOrderResponseSchema,
  });
}

/** MKT-004 · The marketing team records the dispatch: the date (not in the future) and a reference. */
export function dispatchMarketingOrder(
  orderId: string,
  { body, idempotencyKey }: WriteInput<DispatchRequest>,
): Promise<MarketingOrder> {
  return apiRequest({
    dataId: "MKT-004",
    logger: log,
    fn: "dispatchMarketingOrder",
    method: "POST",
    path: `/marketing-orders/${encodeURIComponent(orderId)}/dispatch`,
    body,
    idempotencyKey,
    schema: marketingOrderResponseSchema,
  });
}
