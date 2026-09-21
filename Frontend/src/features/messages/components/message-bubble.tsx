import { Link01Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import type * as React from "react";

import { Icon } from "@/components/ui/icon";
import { formatTime } from "@/lib/format";
import {
  describeResourceType,
  resourceHref,
  type ResourceRef,
} from "@/lib/navigation/resource-href";
import { cn } from "@/lib/utils";

export interface MessageBubbleProps {
  body: string;
  resource: ResourceRef | null;
  /** Null while the message is still being sent. */
  createdAt: string | null;
  mine: boolean;
  /** Read out before the message: "You" or the colleague's name. */
  senderName: string;
  /** Sits close to the previous bubble from the same sender. */
  grouped: boolean;
  /** Shows the time — on the last bubble of a group. */
  showTime: boolean;
}

/** One message: mine on the right in teal, theirs on the left, with any linked record inside. */
export function MessageBubble({
  body,
  resource,
  createdAt,
  mine,
  senderName,
  grouped,
  showTime,
}: MessageBubbleProps): React.JSX.Element {
  const pending = createdAt === null;

  return (
    <div
      className={cn(
        "flex flex-col",
        mine ? "items-end" : "items-start",
        grouped ? "mt-0.5" : "mt-3",
      )}
    >
      <div
        className={cn(
          "flex max-w-xs flex-col gap-2 rounded-2xl px-3.5 py-2 text-sm sm:max-w-md",
          mine
            ? "rounded-br-md bg-primary text-primary-foreground"
            : "rounded-bl-md bg-muted text-foreground",
          pending && "opacity-70",
        )}
      >
        <p className="wrap-break-word whitespace-pre-wrap">
          <span className="sr-only">{mine ? "You" : senderName}: </span>
          {body}
        </p>
        {resource === null ? null : <ResourceCard resource={resource} mine={mine} />}
      </div>
      {pending ? (
        <span className="mt-1 px-1 text-2xs text-subtle-foreground">Sending…</span>
      ) : showTime ? (
        <time
          dateTime={createdAt}
          suppressHydrationWarning
          className="mt-1 px-1 text-2xs text-subtle-foreground tabular-nums"
        >
          {formatTime(createdAt)}
        </time>
      ) : null}
    </div>
  );
}

function ResourceCard({
  resource,
  mine,
}: {
  resource: ResourceRef;
  mine: boolean;
}): React.JSX.Element {
  const href = resourceHref(resource);
  const classes = cn(
    "flex min-w-0 items-center gap-2 rounded-lg border px-2.5 py-2 text-left",
    mine ? "border-primary-foreground/25 bg-primary-foreground/10" : "border-border bg-card",
  );
  const content = (
    <>
      <Icon icon={Link01Icon} size="sm" className="shrink-0" />
      <span className="flex min-w-0 flex-col">
        <span className="text-2xs font-medium tracking-wide uppercase opacity-80">
          {describeResourceType(resource.type)}
        </span>
        <span className="truncate font-medium">{resource.label}</span>
      </span>
    </>
  );

  if (href === null) {
    return <div className={classes}>{content}</div>;
  }

  return (
    <Link
      href={href}
      className={cn(
        classes,
        "focus-ring-inset transition-colors duration-fast",
        mine ? "hover:bg-primary-foreground/20" : "hover:border-border-strong",
      )}
    >
      {content}
    </Link>
  );
}
