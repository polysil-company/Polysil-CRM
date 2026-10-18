import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { getCustomer, getCustomerTimeline, listCustomers } from "./customers.api";
import type { CustomerListParams } from "./customers.schemas";

/** The first page: no cursor yet. */
const FIRST_PAGE: string | null = null;

export const customerKeys = {
  all: ["customers"] as const,
  lists: () => [...customerKeys.all, "list"] as const,
  list: (params: CustomerListParams) => [...customerKeys.lists(), params] as const,
  detail: (customerId: string) => [...customerKeys.all, "detail", customerId] as const,
  timeline: (customerId: string) => [...customerKeys.all, "timeline", customerId] as const,
};

/** LEAD-016 · A page of customers at a time. */
export function customerListQueryOptions(params: CustomerListParams) {
  return infiniteQueryOptions({
    queryKey: customerKeys.list(params),
    queryFn: ({ pageParam, signal }) => listCustomers({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "LEAD-016" },
  });
}

/** LEAD-017 · One customer. */
export function customerDetailQueryOptions(customerId: string) {
  return queryOptions({
    queryKey: customerKeys.detail(customerId),
    queryFn: ({ signal }) => getCustomer(customerId, signal),
    meta: { dataId: "LEAD-017" },
  });
}

/** LEAD-017 · The customer's timeline, older pages on demand. */
export function customerTimelineQueryOptions(customerId: string) {
  return infiniteQueryOptions({
    queryKey: customerKeys.timeline(customerId),
    queryFn: ({ pageParam, signal }) =>
      getCustomerTimeline({ customerId, before: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "LEAD-017" },
  });
}
