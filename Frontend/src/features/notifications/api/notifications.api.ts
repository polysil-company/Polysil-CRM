import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  markNotificationsReadResponseSchema,
  notificationListResponseSchema,
  type MarkNotificationsReadRequest,
  type MarkNotificationsReadResult,
  type NotificationList,
} from "./notifications.schemas";

const log = createLogger({
  file: "features/notifications/api/notifications.api.ts",
  dataId: "NOTIF-001",
});

/** How many notifications the bell shows. */
export const NOTIFICATION_PAGE_SIZE = 20;

/** NOTIF-001 · GET /notifications */
export function listNotifications(signal?: AbortSignal): Promise<NotificationList> {
  return apiRequest({
    dataId: "NOTIF-001",
    logger: log,
    fn: "listNotifications",
    path: "/notifications",
    query: { limit: NOTIFICATION_PAGE_SIZE },
    schema: notificationListResponseSchema,
    signal,
  });
}

/** NOTIF-002 · POST /notifications/read */
export function markNotificationsRead(
  body: MarkNotificationsReadRequest,
): Promise<MarkNotificationsReadResult> {
  return apiRequest({
    dataId: "NOTIF-002",
    logger: log,
    fn: "markNotificationsRead",
    method: "POST",
    path: "/notifications/read",
    body,
    schema: markNotificationsReadResponseSchema,
  });
}
