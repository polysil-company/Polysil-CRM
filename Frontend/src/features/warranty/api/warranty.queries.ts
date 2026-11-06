import { queryOptions } from "@tanstack/react-query";

import { getOrderWarranty, listWarrantyTerms } from "./warranty.api";

/** Query keys for warranty. `warrantyKeys.all` covers every order's warranty and the terms. */
export const warrantyKeys = {
  all: ["warranty"] as const,
  order: (orderId: string) => [...warrantyKeys.all, "order", orderId] as const,
  terms: () => [...warrantyKeys.all, "terms"] as const,
};

/** SO-009 · An order's warranty. */
export function orderWarrantyQueryOptions(orderId: string) {
  return queryOptions({
    queryKey: warrantyKeys.order(orderId),
    queryFn: ({ signal }) => getOrderWarranty(orderId, signal),
    meta: { dataId: "SO-009" },
  });
}

/** MSTR-017 · The warranty periods. */
export function warrantyTermsQueryOptions() {
  return queryOptions({
    queryKey: warrantyKeys.terms(),
    queryFn: ({ signal }) => listWarrantyTerms(signal),
    meta: { dataId: "MSTR-017" },
  });
}
