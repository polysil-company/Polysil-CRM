import { describe, expect, it } from "vitest";

import type {
  AppNotification,
  NotificationList,
} from "@/features/notifications/api/notifications.schemas";

import { markReadLocally, unreadAfterMarking } from "./mark-read";

const READ_AT = "2026-09-15T10:00:00.000Z";

function notification(id: string, readAt: string | null): AppNotification {
  return {
    id,
    kind: "lead_assigned",
    title: `Notification ${id}`,
    body: null,
    actor: null,
    resource: null,
    createdAt: "2026-09-15T09:00:00.000Z",
    readAt,
  };
}

const LIST: NotificationList = {
  items: [notification("a", null), notification("b", null), notification("c", READ_AT)],
  // More unread exist beyond this page.
  unreadCount: 5,
  nextCursor: null,
};

describe("[NOTIF-002] markReadLocally", () => {
  it("marks the chosen unread notifications and lowers the count by as many", () => {
    const next = markReadLocally(LIST, { ids: ["a", "c"] }, "2026-09-15T11:00:00.000Z");

    expect(next.items.map((item) => item.readAt)).toEqual([
      "2026-09-15T11:00:00.000Z",
      null,
      READ_AT,
    ]);
    expect(next.unreadCount).toBe(4);
  });

  it("marks everything and clears the count", () => {
    const next = markReadLocally(LIST, { all: true }, "2026-09-15T11:00:00.000Z");

    expect(next.items.every((item) => item.readAt !== null)).toBe(true);
    expect(next.unreadCount).toBe(0);
  });
});

describe("[NOTIF-002] unreadAfterMarking", () => {
  it("lowers the badge by the unread ones among the ids the list knows", () => {
    // "c" was read already and "z" is not on screen: only "a" counts.
    expect(unreadAfterMarking(5, LIST, { ids: ["a", "c", "z"] })).toBe(4);
  });

  it("clears the badge for everything, and never goes below zero", () => {
    expect(unreadAfterMarking(5, LIST, { all: true })).toBe(0);
    expect(unreadAfterMarking(0, LIST, { ids: ["a", "b"] })).toBe(0);
    expect(unreadAfterMarking(3, undefined, { ids: ["a"] })).toBe(3);
  });
});
