import { queryOptions } from "@tanstack/react-query";

import { listNotifications } from "./notifications.api";

/**
 * How often the bell checks for new notifications. Polling pauses while the tab is
 * hidden (TanStack Query's default) and refetches when the tab comes back.
 * TODO(NOTIF-001): replace with push once the backend chooses a transport.
 */
export const NOTIFICATION_POLL_MS = 30_000;

export const notificationKeys = {
  all: ["notifications"] as const,
  list: () => [...notificationKeys.all, "list"] as const,
};

export function notificationListQueryOptions() {
  return queryOptions({
    queryKey: notificationKeys.list(),
    queryFn: ({ signal }) => listNotifications(signal),
    refetchInterval: NOTIFICATION_POLL_MS,
    staleTime: 15_000,
    meta: { dataId: "NOTIF-001" },
  });
}
