import { queryOptions } from "@tanstack/react-query";

import { getDashboardOverview } from "./dashboard.api";

export const dashboardKeys = {
  all: ["dashboard"] as const,
  overview: () => [...dashboardKeys.all, "overview"] as const,
};

export function dashboardOverviewQueryOptions() {
  return queryOptions({
    queryKey: dashboardKeys.overview(),
    queryFn: ({ signal }) => getDashboardOverview(signal),
    staleTime: 60_000,
    meta: { dataId: "RPT-001" },
  });
}
