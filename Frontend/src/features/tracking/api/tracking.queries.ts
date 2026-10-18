import { queryOptions } from "@tanstack/react-query";

import { getRoute, getTeamLatest } from "./tracking.api";

/** The contract's limit: poll the team map every 60 seconds at most. */
export const TEAM_POLL_MS = 60_000;

/** Query keys for field tracking. `trackingKeys.all` covers the map, routes and visits. */
export const trackingKeys = {
  all: ["tracking"] as const,
  team: () => [...trackingKeys.all, "team"] as const,
  route: (userId: string, date: string) => [...trackingKeys.all, "route", userId, date] as const,
};

/** TRK-001 · The team map, refreshed every minute while it is open. */
export function teamLatestQueryOptions() {
  return queryOptions({
    queryKey: trackingKeys.team(),
    queryFn: ({ signal }) => getTeamLatest(signal),
    refetchInterval: TEAM_POLL_MS,
    meta: { dataId: "TRK-001" },
  });
}

/** TRK-002 · One person's day. */
export function routeQueryOptions(userId: string, date: string) {
  return queryOptions({
    queryKey: trackingKeys.route(userId, date),
    queryFn: ({ signal }) => getRoute({ userId, date }, signal),
    meta: { dataId: "TRK-002" },
  });
}
