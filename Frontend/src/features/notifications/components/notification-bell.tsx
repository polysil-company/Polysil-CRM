"use client";

import {
  ArrowTurnBackwardIcon,
  CancelCircleIcon,
  CheckmarkBadge01Icon,
  CheckmarkCircle02Icon,
  CustomerSupportIcon,
  DiscountTag01Icon,
  Note01Icon,
  Notification01Icon,
  Notification03Icon,
  NotificationOff01Icon,
  PackageIcon,
  Search01Icon,
  SecurityCheckIcon,
  TaskDone01Icon,
  UserAdd01Icon,
} from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { QueryView } from "@/components/patterns/query-view";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Button } from "@/components/ui/button";
import { Icon, type IconGlyph } from "@/components/ui/icon";
import { Popover, PopoverContent, PopoverTitle, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarkNotificationsRead } from "@/features/notifications/api/notifications.mutations";
import {
  NOTIFICATION_POLL_MS,
  notificationCountQueryOptions,
  notificationListQueryOptions,
} from "@/features/notifications/api/notifications.queries";
import {
  NOTIFICATION_KINDS,
  type AppNotification,
  type NotificationKind,
} from "@/features/notifications/api/notifications.schemas";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { describeResourceType, resourceHref } from "@/lib/navigation/resource-href";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/notifications/components/notification-bell.tsx",
  dataId: "NOTIF-001",
});

/** One icon per known kind — adding a kind to the contract without an icon is a type error. */
const KIND_ICONS: Readonly<Record<NotificationKind, IconGlyph>> = {
  lead_assigned: UserAdd01Icon,
  task_assigned: TaskDone01Icon,
  lead_note: Note01Icon,
  approval_requested: CheckmarkBadge01Icon,
  order_approved: PackageIcon,
  order_returned: ArrowTurnBackwardIcon,
  discount_approved: DiscountTag01Icon,
  discount_returned: ArrowTurnBackwardIcon,
  complaint_assigned: CustomerSupportIcon,
  complaint_to_check: Search01Icon,
  complaint_to_qc: SecurityCheckIcon,
  complaint_returned: ArrowTurnBackwardIcon,
  complaint_qc_approved: CheckmarkCircle02Icon,
  complaint_qc_rejected: CancelCircleIcon,
};

/** A kind the backend added before the app knew about it gets the plain bell. */
function kindIcon(kind: string): IconGlyph {
  const known = NOTIFICATION_KINDS.find((candidate) => candidate === kind);
  return known === undefined ? Notification01Icon : KIND_ICONS[known];
}

/** Above this the badge reads "99+". */
const MAX_BADGE_COUNT = 99;

/**
 * NOTIF-001 · The bell in the top bar: unread count, the latest notifications, and
 * "Mark all as read". The badge polls the count alone; the list is read when the bell opens
 * and polled only while it stays open (see notifications.queries).
 */
export function NotificationBell(): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const count = useQuery(notificationCountQueryOptions());
  const query = useQuery({
    ...notificationListQueryOptions(),
    enabled: open,
    refetchInterval: open ? NOTIFICATION_POLL_MS : false,
  });
  const markRead = useMarkNotificationsRead();
  // Whichever answered last knows the count best.
  const unread =
    query.data !== undefined && query.dataUpdatedAt > count.dataUpdatedAt
      ? query.data.unreadCount
      : (count.data ?? 0);
  const label = unread === 0 ? "Notifications" : `Notifications, ${formatNumber(unread)} unread`;

  const markAsRead = (target: "all" | string): void => {
    log.info(
      "markAsRead",
      target === "all" ? "Marking all notifications as read" : "Marking a notification as read",
    );
    markRead.mutate(target === "all" ? { all: true } : { ids: [target] }, {
      onError: () => {
        toast.error("Couldn't mark as read", {
          description: "Check your connection and try again.",
        });
      },
    });
  };

  const handleOpen = (notification: AppNotification, navigates: boolean): void => {
    if (notification.readAt === null) {
      markAsRead(notification.id);
    }
    if (navigates) {
      setOpen(false);
    }
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={<Button variant="ghost" size="icon-md" aria-label={label} className="relative" />}
      >
        <Icon icon={Notification03Icon} />
        {unread > 0 ? (
          <span
            aria-hidden="true"
            className="absolute top-1 right-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-2xs font-semibold text-primary-foreground tabular-nums ring-2 ring-panel"
          >
            {unread > MAX_BADGE_COUNT ? `${String(MAX_BADGE_COUNT)}+` : formatNumber(unread)}
          </span>
        ) : null}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 max-w-(--available-width) gap-0 p-0">
        <div className="flex items-center justify-between gap-2 border-b border-border py-2 pr-2 pl-4">
          <PopoverTitle>Notifications</PopoverTitle>
          <Button
            variant="ghost"
            size="xs"
            disabled={unread === 0}
            onClick={() => {
              markAsRead("all");
            }}
          >
            Mark all as read
          </Button>
        </div>
        <div className="max-h-96 scrollbar-thin overflow-y-auto">
          <QueryView
            query={query}
            pending={<NotificationListSkeleton />}
            isEmpty={(list) => list.items.length === 0}
            empty={
              <EmptyState
                icon={NotificationOff01Icon}
                title="You're all caught up"
                description="Approvals waiting on you and work assigned to you will show up here."
                className="py-10"
              />
            }
            renderError={(error, retry) => (
              <ErrorState error={error} onRetry={retry} className="py-8" />
            )}
          >
            {(list) => (
              <ul aria-label="Latest notifications" className="divide-y divide-border">
                {list.items.map((notification) => (
                  <li key={notification.id}>
                    <NotificationItem
                      notification={notification}
                      onOpen={(navigates) => {
                        handleOpen(notification, navigates);
                      }}
                    />
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function NotificationItem({
  notification,
  onOpen,
}: {
  notification: AppNotification;
  onOpen: (navigates: boolean) => void;
}): React.JSX.Element {
  const unread = notification.readAt === null;
  const href = notification.resource === null ? null : resourceHref(notification.resource);
  const rowClasses = "flex w-full items-start gap-3 px-4 py-3 text-left";
  const interactiveClasses = "focus-ring-inset transition-colors duration-fast hover:bg-accent";

  const content = (
    <>
      <span
        aria-hidden="true"
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full",
          unread
            ? "bg-primary-soft text-primary-soft-foreground"
            : "bg-muted text-muted-foreground",
        )}
      >
        <Icon icon={kindIcon(notification.kind)} size="sm" />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span
          className={cn(
            "text-sm",
            unread ? "font-medium text-foreground" : "text-muted-foreground",
          )}
        >
          {unread ? <span className="sr-only">Unread: </span> : null}
          {notification.title}
        </span>
        {notification.body === null ? null : (
          <span className="line-clamp-2 text-xs text-muted-foreground">{notification.body}</span>
        )}
        {/* Muted, not subtle: subtle text falls below 4.5:1 on the dark popover. */}
        <span className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
          <RelativeDate value={notification.createdAt} className="text-xs text-muted-foreground" />
          {notification.resource === null ? null : (
            <>
              <span aria-hidden="true">·</span>
              <span className="truncate">
                {describeResourceType(notification.resource.type)} {notification.resource.label}
              </span>
            </>
          )}
        </span>
      </span>
      {unread ? (
        <span aria-hidden="true" className="mt-2 size-2 shrink-0 rounded-full bg-primary" />
      ) : null}
    </>
  );

  if (href !== null) {
    return (
      <Link
        href={href}
        onClick={() => {
          onOpen(true);
        }}
        className={cn(rowClasses, interactiveClasses)}
      >
        {content}
      </Link>
    );
  }

  if (unread) {
    return (
      <button
        type="button"
        onClick={() => {
          onOpen(false);
        }}
        className={cn(rowClasses, interactiveClasses)}
      >
        {content}
      </button>
    );
  }

  return <div className={rowClasses}>{content}</div>;
}

export function NotificationListSkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading notifications" className="divide-y divide-border">
      {[0, 1, 2].map((row) => (
        <div key={row} className="flex items-start gap-3 px-4 py-3">
          <Skeleton className="size-8 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3.5 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-3 w-16" />
          </div>
        </div>
      ))}
    </div>
  );
}
