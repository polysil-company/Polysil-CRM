import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import { dashboardOverviewSchema, type DashboardOverview } from "./dashboard.schemas";

const log = createLogger({ file: "features/dashboard/api/dashboard.api.ts", dataId: "RPT-001" });

/** RPT-001 · GET /dashboard/overview — already scoped to the user's region by the backend. */
export function getDashboardOverview(signal?: AbortSignal): Promise<DashboardOverview> {
  return apiRequest({
    dataId: "RPT-001",
    logger: log,
    fn: "getDashboardOverview",
    path: "/dashboard/overview",
    schema: dashboardOverviewSchema,
    signal,
  });
}
