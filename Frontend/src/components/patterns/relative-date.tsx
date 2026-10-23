"use client";

import type * as React from "react";

import { useNow } from "@/hooks/use-now";
import {
  EMPTY_VALUE,
  formatDateTime,
  formatRelativeTime,
  isPast,
  toDate,
  type DateInput,
} from "@/lib/format";
import { cn } from "@/lib/utils";

export interface RelativeDateProps {
  value: DateInput;
  /** Colour dates in the past as overdue — for follow-ups and deadlines. */
  highlightOverdue?: boolean;
  className?: string;
}

/** "in 2 days", "3 hours ago" — the exact IST date and time on hover. */
export function RelativeDate({
  value,
  highlightOverdue = false,
  className,
}: RelativeDateProps): React.JSX.Element {
  const now = new Date(useNow());
  const date = toDate(value);

  if (!date) {
    return <span className={cn("text-sm text-subtle-foreground", className)}>{EMPTY_VALUE}</span>;
  }

  const overdue = highlightOverdue && isPast(date, now);

  return (
    <time
      dateTime={date.toISOString()}
      title={formatDateTime(date)}
      suppressHydrationWarning
      className={cn(
        "text-sm whitespace-nowrap tabular-nums",
        overdue ? "font-medium text-danger" : "text-foreground",
        className,
      )}
    >
      {formatRelativeTime(date, now)}
    </time>
  );
}
