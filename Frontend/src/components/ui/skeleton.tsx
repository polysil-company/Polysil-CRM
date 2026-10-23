import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Loading placeholder with a subtle shimmer (static under reduced motion).
 *
 * Rule: a skeleton must mirror the layout of the component it stands in for —
 * same heights, gaps and column widths — so nothing shifts when data arrives.
 * Each data component exports its own `…Skeleton` built from this primitive.
 * The loading container carries `aria-busy`; skeleton blocks stay hidden
 * from screen readers.
 */
export function Skeleton({ className, ...props }: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="skeleton"
      aria-hidden="true"
      className={cn("skeleton-shimmer rounded-sm", className)}
      {...props}
    />
  );
}
