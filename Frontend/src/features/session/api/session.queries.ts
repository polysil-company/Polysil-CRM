import { queryOptions } from "@tanstack/react-query";

import { fetchSession } from "./session.api";

export const sessionKeys = {
  all: ["session"] as const,
  current: () => [...sessionKeys.all, "current"] as const,
};

/** The signed-in user rarely changes during a visit: keep it fresh for 5 minutes. */
export function sessionQueryOptions() {
  return queryOptions({
    queryKey: sessionKeys.current(),
    queryFn: ({ signal }) => fetchSession(signal),
    staleTime: 5 * 60_000,
    meta: { dataId: "AUTH-002" },
  });
}
