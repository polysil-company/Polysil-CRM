import type {
  MarkNotificationsReadRequest,
  NotificationList,
} from "@/features/notifications/api/notifications.schemas";

/**
 * The list as it will look once the backend marks `request` as read, so the bell
 * updates the moment someone clicks — the server's answer then confirms it.
 */
export function markReadLocally(
  list: NotificationList,
  request: MarkNotificationsReadRequest,
  readAt: string,
): NotificationList {
  const targets = "all" in request ? null : new Set(request.ids);
  let newlyRead = 0;

  const items = list.items.map((item) => {
    if (item.readAt !== null || (targets !== null && !targets.has(item.id))) {
      return item;
    }
    newlyRead += 1;
    return { ...item, readAt };
  });

  return {
    ...list,
    items,
    unreadCount: targets === null ? 0 : Math.max(0, list.unreadCount - newlyRead),
  };
}
