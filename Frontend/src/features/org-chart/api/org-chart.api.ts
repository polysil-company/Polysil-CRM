import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import { orgChartSchema, type OrgChart, type OrgChartParams } from "./org-chart.schemas";

const log = createLogger({ file: "features/org-chart/api/org-chart.api.ts", dataId: "ADMN-008" });

/**
 * ADMN-008 · GET /users/org-chart: any staff member's own picture, someone's below them
 * (`user_id`), or the whole company (`view=company`, for a `users.view` global holder). A
 * person outside what the reader may see is a 404: "no reporting line to show".
 */
export function getOrgChart(params: OrgChartParams, signal?: AbortSignal): Promise<OrgChart> {
  return apiRequest({
    dataId: "ADMN-008",
    logger: log,
    fn: "getOrgChart",
    path: "/users/org-chart",
    query: params.company ? { view: "company" } : { user_id: params.userId ?? undefined },
    schema: orgChartSchema,
    signal,
  });
}
