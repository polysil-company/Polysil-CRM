import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  CUSTOMER_PAGE_SIZE,
  CUSTOMER_SEARCH_MIN_LENGTH,
  customerDetailSchema,
  customerPageSchema,
  customerTimelinePageSchema,
  type CustomerDetail,
  type CustomerListParams,
  type CustomerPage,
  type CustomerPatchRequest,
  type CustomerTimelinePage,
} from "./customers.schemas";

const log = createLogger({ file: "features/customers/api/customers.api.ts", dataId: "LEAD-016" });

const TIMELINE_PAGE_SIZE = 50;

function customerPath(customerId: string): `/${string}` {
  return `/customers/${encodeURIComponent(customerId)}`;
}

function warnSkipped(
  fn: string,
  dataId: "LEAD-016" | "LEAD-017",
  skipped: number,
  kept: number,
): void {
  if (skipped > 0) {
    log.warn(fn, `left out ${String(skipped)} row(s) that did not match the contract`, {
      dataId,
      context: { skipped, kept },
    });
  }
}

/**
 * LEAD-016 · Customers you can see one lead of, newest first. `q` (name or mobile) is sent
 * only once it is long enough to search.
 */
export async function listCustomers(
  params: CustomerListParams & { readonly cursor: string | null },
  signal?: AbortSignal,
): Promise<CustomerPage> {
  const q = params.q.trim();
  const page = await apiRequest({
    dataId: "LEAD-016",
    logger: log,
    fn: "listCustomers",
    path: "/customers",
    query: {
      q: q.length >= CUSTOMER_SEARCH_MIN_LENGTH ? q : null,
      territory_id: params.territoryId,
      limit: CUSTOMER_PAGE_SIZE,
      cursor: params.cursor,
    },
    schema: customerPageSchema,
    signal,
  });
  warnSkipped("listCustomers", "LEAD-016", page.skipped, page.items.length);
  return page;
}

/** LEAD-017 · A customer with its leads, quotations and orders you can see. 404 if none. */
export function getCustomer(customerId: string, signal?: AbortSignal): Promise<CustomerDetail> {
  return apiRequest({
    dataId: "LEAD-017",
    logger: log,
    fn: "getCustomer",
    path: customerPath(customerId),
    schema: customerDetailSchema,
    signal,
  });
}

/** LEAD-017 · Everything on the customer's leads, and to the customer, newest first. */
export async function getCustomerTimeline(
  { customerId, before }: { readonly customerId: string; readonly before: string | null },
  signal?: AbortSignal,
): Promise<CustomerTimelinePage> {
  const page = await apiRequest({
    dataId: "LEAD-017",
    logger: log,
    fn: "getCustomerTimeline",
    path: `${customerPath(customerId)}/timeline`,
    query: { limit: TIMELINE_PAGE_SIZE, before },
    schema: customerTimelinePageSchema,
    signal,
  });
  warnSkipped("getCustomerTimeline", "LEAD-017", page.skipped, page.items.length);
  return page;
}

/** LEAD-018 · Correct the details or record consent (staff with leads edit; a dealer gets 403). */
export function patchCustomer({
  customerId,
  body,
  idempotencyKey,
}: {
  readonly customerId: string;
  readonly body: CustomerPatchRequest;
  readonly idempotencyKey: string;
}): Promise<CustomerDetail> {
  return apiRequest({
    dataId: "LEAD-018",
    logger: log,
    fn: "patchCustomer",
    method: "PATCH",
    path: customerPath(customerId),
    body,
    idempotencyKey,
    schema: customerDetailSchema,
  });
}
