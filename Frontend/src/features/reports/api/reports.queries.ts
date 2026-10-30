import { queryOptions } from "@tanstack/react-query";

import { getLead360, getReport } from "./reports.api";
import type { ReportName, ReportParams } from "./reports.schemas";

export const reportKeys = {
  all: ["reports"] as const,
  report: (name: ReportName, params: ReportParams) => [...reportKeys.all, name, params] as const,
  lead360: (leadId: string) => [...reportKeys.all, "lead-360", leadId] as const,
};

/** RPT-002 · One report. A report the user may not run answers 403 and is not retried. */
export function reportQueryOptions<N extends ReportName>(name: N, params: ReportParams) {
  return queryOptions({
    queryKey: reportKeys.report(name, params),
    queryFn: ({ signal }) => getReport(name, params, signal),
    meta: { dataId: "RPT-002" },
  });
}

/** RPT-003 · A lead's 360° tiles. */
export function lead360QueryOptions(leadId: string) {
  return queryOptions({
    queryKey: reportKeys.lead360(leadId),
    queryFn: ({ signal }) => getLead360(leadId, signal),
    meta: { dataId: "RPT-003" },
  });
}
