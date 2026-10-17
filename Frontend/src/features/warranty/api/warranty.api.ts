import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  orderWarrantySchema,
  warrantyTermsSchema,
  type OrderWarranty,
  type SetWarrantyTermRequest,
  type WarrantyTerm,
} from "./warranty.schemas";

const log = createLogger({ file: "features/warranty/api/warranty.api.ts", dataId: "SO-009" });

/** SO-009 · An order's warranty, line by line (needs sales_orders.view and dispatch.view). */
export function getOrderWarranty(orderId: string, signal?: AbortSignal): Promise<OrderWarranty> {
  return apiRequest({
    dataId: "SO-009",
    logger: log,
    fn: "getOrderWarranty",
    path: `/orders/${encodeURIComponent(orderId)}/warranty`,
    schema: orderWarrantySchema,
    signal,
  });
}

/** MSTR-017 · Every warranty period, the default first (masters.view). */
export function listWarrantyTerms(signal?: AbortSignal): Promise<WarrantyTerm[]> {
  return apiRequest({
    dataId: "MSTR-017",
    logger: log,
    fn: "listWarrantyTerms",
    path: "/warranty-terms",
    schema: warrantyTermsSchema,
    signal,
  });
}

/**
 * MSTR-017 · Set a category's period, or the default's, from tomorrow or later (masters.edit).
 * Returns the whole list. 409 term_exists; 422 on `effective_from` or `months`.
 */
export function setWarrantyTerm({
  body,
  idempotencyKey,
}: {
  readonly body: SetWarrantyTermRequest;
  readonly idempotencyKey: string;
}): Promise<WarrantyTerm[]> {
  return apiRequest({
    dataId: "MSTR-017",
    logger: log,
    fn: "setWarrantyTerm",
    method: "POST",
    path: "/warranty-terms",
    body,
    idempotencyKey,
    schema: warrantyTermsSchema,
  });
}
