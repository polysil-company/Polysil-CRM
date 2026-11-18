import { queryOptions } from "@tanstack/react-query";

import { getOrgChart } from "./org-chart.api";
import type { OrgChartParams } from "./org-chart.schemas";

export const orgChartKeys = {
  all: ["org-chart"] as const,
  chart: (params: OrgChartParams) => [...orgChartKeys.all, params] as const,
};

/** ADMN-008 · Whose picture is in the key, so moving between people keeps each one cached. */
export function orgChartQueryOptions(params: OrgChartParams) {
  return queryOptions({
    queryKey: orgChartKeys.chart(params),
    queryFn: ({ signal }) => getOrgChart(params, signal),
    meta: { dataId: "ADMN-008" },
  });
}
