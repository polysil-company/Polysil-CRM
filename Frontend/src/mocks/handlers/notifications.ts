import { http, HttpResponse } from "msw";

import {
  markNotificationsReadRequestSchema,
  type MarkNotificationsReadResponse,
  type NotificationListResponse,
  type NotificationWire,
} from "@/features/notifications/api/notifications.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

function positiveInt(raw: string | null, fallback: number): number {
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

/** The seeded notifications are staff work items; partner roles see none in the mock. */
function visibleNotifications(): NotificationWire[] {
  return isPartnerRole(readMockRole()) ? [] : mockDb.notifications;
}

function isUnread(notification: NotificationWire): boolean {
  return (notification.read_at ?? null) === null;
}

export const notificationHandlers = [
  http.get(buildApiUrl("/notifications"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    if (scenario === "contract") {
      // Deliberately wrong shape: exercises CONTRACT_VIOLATION handling end to end.
      return HttpResponse.json({ data: [{ id: 7, title: null }], meta: {} });
    }

    const url = new URL(request.url);
    const items =
      scenario === "empty"
        ? []
        : [...visibleNotifications()].sort(
            (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
          );
    const limit = Math.min(100, positiveInt(url.searchParams.get("limit"), 20));
    const shown = url.searchParams.get("unread") === "true" ? items.filter(isUnread) : items;

    const body: NotificationListResponse = {
      data: shown.slice(0, limit),
      // All the unread ones, not only this page, as the backend counts them.
      meta: { unread_count: items.filter(isUnread).length, next_cursor: null },
    };
    return HttpResponse.json(body);
  }),

  http.post(buildApiUrl("/notifications/read"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const payload: unknown = await request.json();
    const parsed = markNotificationsReadRequestSchema.safeParse(payload);
    if (!parsed.success) {
      // The backend's 422 for both or neither of `ids` and `all`.
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        ids: "send either ids or all",
      });
    }

    const readAt = new Date().toISOString();
    const targets = "all" in parsed.data ? null : new Set(parsed.data.ids);
    mockDb.notifications = mockDb.notifications.map((notification) =>
      isUnread(notification) && (targets === null || targets.has(notification.id))
        ? { ...notification, read_at: readAt }
        : notification,
    );

    const body: MarkNotificationsReadResponse = {
      data: { unread_count: visibleNotifications().filter(isUnread).length },
    };
    return HttpResponse.json(body);
  }),
];
