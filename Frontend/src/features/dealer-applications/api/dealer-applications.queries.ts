import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getDealerApplication, listDealerApplications } from "./dealer-applications.api";
import type { DealerApplicationListParams } from "./dealer-applications.schemas";

/** A write to one application moves it in the list too: mutations invalidate `all`. */
export const dealerApplicationKeys = {
  all: ["dealer-applications"] as const,
  list: (params: DealerApplicationListParams) =>
    [...dealerApplicationKeys.all, "list", params] as const,
  detail: (applicationId: string) =>
    [...dealerApplicationKeys.all, "detail", applicationId] as const,
};

/** CHNL-007 · The applications in scope (at most 200), filtered. */
export function dealerApplicationListQueryOptions(params: DealerApplicationListParams) {
  return queryOptions({
    queryKey: dealerApplicationKeys.list(params),
    queryFn: ({ signal }) => listDealerApplications(params, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "CHNL-007" },
  });
}

/** CHNL-007 · One application. */
export function dealerApplicationQueryOptions(applicationId: string) {
  return queryOptions({
    queryKey: dealerApplicationKeys.detail(applicationId),
    queryFn: ({ signal }) => getDealerApplication(applicationId, signal),
    meta: { dataId: "CHNL-007" },
  });
}
