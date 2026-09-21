import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Based on shadcn/ui (base-nova) — restyled. Layout primitive for empty and
 * error states; compose with `EmptyState` / `ErrorState` rather than directly.
 */
export function Empty({ className, ...props }: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="empty"
      className={cn(
        "flex w-full min-w-0 flex-1 flex-col items-center justify-center gap-4 px-6 py-12 text-center text-balance",
        className,
      )}
      {...props}
    />
  );
}

export function EmptyMedia({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="empty-media"
      className={cn(
        "flex size-10 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground shadow-xs [&_svg]:size-5",
        className,
      )}
      {...props}
    />
  );
}

export function EmptyTitle({
  className,
  children,
  ...props
}: React.ComponentProps<"h3">): React.JSX.Element {
  return (
    <h3
      data-slot="empty-title"
      className={cn("text-base font-semibold text-foreground", className)}
      {...props}
    >
      {children}
    </h3>
  );
}

export function EmptyDescription({
  className,
  ...props
}: React.ComponentProps<"p">): React.JSX.Element {
  return (
    <p
      data-slot="empty-description"
      className={cn("max-w-sm text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

export function EmptyContent({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="empty-content"
      className={cn("flex flex-wrap items-center justify-center gap-2", className)}
      {...props}
    />
  );
}
