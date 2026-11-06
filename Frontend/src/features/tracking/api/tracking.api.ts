import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import { routeSchema, teamLatestSchema, type Route, type TeamMember } from "./tracking.schemas";

const log = createLogger({ file: "features/tracking/api/tracking.api.ts", dataId: "TRK-001" });

/** TRK-001 · Everyone the user may track, with their last position while on duty. Logged. */
export function getTeamLatest(signal?: AbortSignal): Promise<TeamMember[]> {
  return apiRequest({
    dataId: "TRK-001",
    logger: log,
    fn: "getTeamLatest",
    path: "/tracking/team/latest",
    schema: teamLatestSchema,
    signal,
  });
}

/** TRK-002 · One person's Indian calendar day. 404 outside the user's team. Logged. */
export function getRoute(
  { userId, date }: { readonly userId: string; readonly date: string },
  signal?: AbortSignal,
): Promise<Route> {
  return apiRequest({
    dataId: "TRK-002",
    logger: log,
    fn: "getRoute",
    path: `/tracking/users/${encodeURIComponent(userId)}/route`,
    query: { date },
    schema: routeSchema,
    signal,
  });
}
