import { queryOptions } from "@tanstack/react-query";

import { countUnreadNotifications, listNotifications } from "./notifications.api";

/**
 * How often the bell checks the unread count. Polling pauses while the tab is hidden
 * (TanStack Query's default) and refetches when the tab comes back. The backend has no
 * push, and asks the bell to poll `?limit=1` (backend/docs/api/notifications.md).
 */
export const NOTIFICATION_POLL_MS = 30_000;

export const notificationKeys = {
  all: ["notifications"] as const,
  list: () => [...notificationKeys.all, "list"] as const,
  unreadCount: () => [...notificationKeys.all, "unread-count"] as const,
};

/** The badge: one notification's worth of data, every half minute. */
export function notificationCountQueryOptions() {
  return queryOptions({
    queryKey: notificationKeys.unreadCount(),
    queryFn: ({ signal }) => countUnreadNotifications(signal),
    refetchInterval: NOTIFICATION_POLL_MS,
    staleTime: 15_000,
    meta: { dataId: "NOTIF-001" },
  });
}

/** The latest notifications, read when the bell opens and polled only while it is open. */
export function notificationListQueryOptions() {
  return queryOptions({
    queryKey: notificationKeys.list(),
    queryFn: ({ signal }) => listNotifications(signal),
    staleTime: 15_000,
    meta: { dataId: "NOTIF-001" },
  });
}
