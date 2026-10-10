import { z } from "zod";

import type { ResourceRef } from "@/lib/navigation/resource-href";

/**
 * NOTIF-001, NOTIF-002 · In-app notifications, as the backend serves them since BE-009
 * (backend/docs/api/notifications.md). Unknown `kind` and resource `type` values are kept and
 * shown generically, so the backend can add events without a frontend release. There is no
 * push: the bell polls the unread count.
 */

const isoDateTime = z.iso.datetime({ offset: true });
const count = z.number().int().nonnegative();

/** The events the backend sends today, each with its own icon. Others still render. */
export const NOTIFICATION_KINDS = [
  "lead_assigned",
  "task_assigned",
  "lead_note",
  "approval_requested",
  "order_approved",
  "order_returned",
  "discount_approved",
  "discount_returned",
  "complaint_assigned",
  "complaint_to_check",
  "complaint_to_qc",
  "complaint_returned",
  "complaint_qc_approved",
  "complaint_qc_rejected",
] as const;
export type NotificationKind = (typeof NOTIFICATION_KINDS)[number];

const resourceRefSchema = z.object({
  type: z.string().min(1),
  id: z.string().min(1),
  label: z.string().min(1),
});

export const notificationWireSchema = z.object({
  id: z.string().min(1),
  kind: z.string().min(1),
  title: z.string().min(1),
  body: z.string().nullish(),
  /** Null for a dealer told of a decision: a dealer is never told who decided. */
  actor: z.object({ id: z.string().min(1), full_name: z.string() }).nullish(),
  resource: resourceRefSchema.nullish(),
  created_at: isoDateTime,
  read_at: isoDateTime.nullish(),
});

/** One notification as the backend sends it (and the mock backend must produce it). */
export type NotificationWire = z.input<typeof notificationWireSchema>;

export interface AppNotification {
  readonly id: string;
  readonly kind: string;
  readonly title: string;
  readonly body: string | null;
  /** Who caused it, when a person did. */
  readonly actor: { readonly id: string; readonly name: string } | null;
  readonly resource: ResourceRef | null;
  readonly createdAt: string;
  /** Null while unread. */
  readonly readAt: string | null;
}

export interface NotificationList {
  /** Newest first. */
  readonly items: readonly AppNotification[];
  /** Across all notifications, not only this page. */
  readonly unreadCount: number;
  readonly nextCursor: string | null;
}

function toNotification(wire: z.output<typeof notificationWireSchema>): AppNotification {
  return {
    id: wire.id,
    kind: wire.kind,
    title: wire.title,
    body: wire.body ?? null,
    // A blank name (someone outside the reader's view of people) names nobody.
    actor:
      wire.actor && wire.actor.full_name.trim() !== ""
        ? { id: wire.actor.id, name: wire.actor.full_name.trim() }
        : null,
    resource: wire.resource ?? null,
    createdAt: wire.created_at,
    readAt: wire.read_at ?? null,
  };
}

/** NOTIF-001 · GET /notifications */
export const notificationListResponseSchema = z
  .object({
    data: z.array(notificationWireSchema),
    meta: z.object({ unread_count: count, next_cursor: z.string().nullish() }),
  })
  .transform(({ data, meta }): NotificationList => ({
    items: data.map(toNotification),
    unreadCount: meta.unread_count,
    nextCursor: meta.next_cursor ?? null,
  }));

export type NotificationListResponse = z.input<typeof notificationListResponseSchema>;

/** NOTIF-002 · POST /notifications/read — some by id, or all at once. */
export const markNotificationsReadRequestSchema = z.union([
  z.object({ ids: z.array(z.string().min(1)).min(1) }),
  z.object({ all: z.literal(true) }),
]);

export type MarkNotificationsReadRequest = z.infer<typeof markNotificationsReadRequestSchema>;

export interface MarkNotificationsReadResult {
  readonly unreadCount: number;
}

export const markNotificationsReadResponseSchema = z
  .object({ data: z.object({ unread_count: count }) })
  .transform(({ data }): MarkNotificationsReadResult => ({ unreadCount: data.unread_count }));

export type MarkNotificationsReadResponse = z.input<typeof markNotificationsReadResponseSchema>;
