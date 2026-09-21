import { afterEach, describe, expect, it } from "vitest";

import { writeMockRole } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";

import { listNotifications, markNotificationsRead } from "./notifications.api";

describe("[NOTIF-001] listNotifications", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("returns the newest first, with the unread count", async () => {
    const list = await listNotifications();

    expect(list.items.length).toBeGreaterThan(0);
    const created = list.items.map((item) => Date.parse(item.createdAt));
    expect(created).toEqual([...created].sort((a, b) => b - a));
    expect(list.unreadCount).toBe(list.items.filter((item) => item.readAt === null).length);
  });

  it("shows partner users none of the staff work items", async () => {
    writeMockRole("dealer");

    const list = await listNotifications();

    expect(list.items).toEqual([]);
    expect(list.unreadCount).toBe(0);
  });
});

describe("[NOTIF-002] markNotificationsRead", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("marks one notification as read", async () => {
    const before = await listNotifications();
    const unread = before.items.find((item) => item.readAt === null);
    if (unread === undefined) {
      throw new Error("The mock has no unread notification");
    }

    const result = await markNotificationsRead({ ids: [unread.id] });

    expect(result.unreadCount).toBe(before.unreadCount - 1);
    const after = await listNotifications();
    expect(after.items.find((item) => item.id === unread.id)?.readAt).toEqual(expect.any(String));
  });

  it("marks everything as read", async () => {
    const result = await markNotificationsRead({ all: true });

    expect(result.unreadCount).toBe(0);
    const after = await listNotifications();
    expect(after.items.every((item) => item.readAt !== null)).toBe(true);
  });
});
