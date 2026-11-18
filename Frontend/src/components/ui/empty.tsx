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

export interface EmptyTitleProps extends React.ComponentProps<"h3"> {
  /** 2 when the empty state is the whole page, under the top bar's h1; 3 inside a section. */
  level?: 1 | 2 | 3;
}

export function EmptyTitle({
  level = 3,
  className,
  children,
  ...props
}: EmptyTitleProps): React.JSX.Element {
  const Heading = level === 1 ? "h1" : level === 2 ? "h2" : "h3";
  return (
    <Heading
      data-slot="empty-title"
      className={cn("text-base font-semibold text-foreground", className)}
      {...props}
    >
      {children}
    </Heading>
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
