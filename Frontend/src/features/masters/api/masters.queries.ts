import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { getScoring, listOffices } from "./masters.api";
import type { OfficeListParams } from "./masters.schemas";

export const masterKeys = {
  all: ["masters"] as const,
  scoring: () => [...masterKeys.all, "scoring"] as const,
  offices: () => [...masterKeys.all, "offices"] as const,
  officeList: (params: Omit<OfficeListParams, "cursor">) =>
    [...masterKeys.offices(), "list", params] as const,
};

/** MSTR-010 · The lead score's settings. */
export function scoringQueryOptions() {
  return queryOptions({
    queryKey: masterKeys.scoring(),
    queryFn: ({ signal }) => getScoring(signal),
    meta: { dataId: "MSTR-010" },
  });
}

const FIRST_PAGE: string | null = null;

/** MSTR-011 · The office tree, a page at a time. */
export function officeListQueryOptions(params: Omit<OfficeListParams, "cursor">) {
  return infiniteQueryOptions({
    queryKey: masterKeys.officeList(params),
    queryFn: ({ pageParam, signal }) => listOffices({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "MSTR-011" },
  });
}
