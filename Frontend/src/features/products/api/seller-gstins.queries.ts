import { queryOptions } from "@tanstack/react-query";

import { listSellerGstins } from "./seller-gstins.api";

/** Query keys for our GST registrations and their LUTs. */
export const sellerGstinKeys = {
  all: ["seller-gstins"] as const,
  list: () => [...sellerGstinKeys.all, "list"] as const,
};

/** MSTR-018 · Our registrations with their LUTs. */
export function sellerGstinsQueryOptions() {
  return queryOptions({
    queryKey: sellerGstinKeys.list(),
    queryFn: ({ signal }) => listSellerGstins(signal),
    meta: { dataId: "MSTR-018" },
  });
}
