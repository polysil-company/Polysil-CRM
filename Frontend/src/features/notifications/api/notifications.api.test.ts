import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { buildApiUrl } from "@/lib/api/url";
import { writeMockRole } from "@/lib/dev/mock-settings";
import { resetMockDb } from "@/mocks/db";
import { server } from "@/mocks/node";

import {
  countUnreadNotifications,
  listNotifications,
  markNotificationsRead,
} from "./notifications.api";

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

  it("reads the backend's own page, with a nameless actor named nobody", async () => {
    server.use(
      http.get(buildApiUrl("/notifications"), () =>
        HttpResponse.json({
          data: [
            {
              id: "4f1d",
              kind: "order_returned",
              title: "Sales order SO/GJ/2026-27/00041 was returned",
              body: null,
              actor: { id: "u-9", full_name: "" },
              resource: { type: "sales_order", id: "o-41", label: "SO/GJ/2026-27/00041" },
              created_at: "2026-10-02T05:30:00Z",
              read_at: null,
            },
          ],
          meta: { unread_count: 7, next_cursor: "abc" },
        }),
      ),
    );

    const list = await listNotifications();

    expect(list.unreadCount).toBe(7);
    expect(list.nextCursor).toBe("abc");
    expect(list.items[0]).toMatchObject({ kind: "order_returned", actor: null, readAt: null });
  });

  it("shows partner users none of the staff work items", async () => {
    writeMockRole("dealer");

    const list = await listNotifications();

    expect(list.items).toEqual([]);
    expect(list.unreadCount).toBe(0);
  });
});

describe("[NOTIF-001] countUnreadNotifications", () => {
  afterEach(() => {
    resetMockDb();
  });

  it("asks for one notification and answers the unread count, as the backend asks the bell to poll", async () => {
    let sent: URL | undefined;
    server.use(
      // Notes the request, then falls through to the mock backend's own handler.
      http.get(buildApiUrl("/notifications"), ({ request }) => {
        sent = new URL(request.url);
      }),
    );

    const count = await countUnreadNotifications();

    expect(sent?.searchParams.get("limit")).toBe("1");
    expect(count).toBe((await listNotifications()).unreadCount);
    expect(count).toBeGreaterThan(0);
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
