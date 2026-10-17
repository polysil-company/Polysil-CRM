import { queryOptions } from "@tanstack/react-query";

import { getScoring } from "./masters.api";

export const masterKeys = {
  all: ["masters"] as const,
  scoring: () => [...masterKeys.all, "scoring"] as const,
};

/** MSTR-010 · The lead score's settings. */
export function scoringQueryOptions() {
  return queryOptions({
    queryKey: masterKeys.scoring(),
    queryFn: ({ signal }) => getScoring(signal),
    meta: { dataId: "MSTR-010" },
  });
}
