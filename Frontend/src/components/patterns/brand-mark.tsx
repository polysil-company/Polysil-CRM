import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Placeholder mark — a water droplet on the primary colour.
 * TODO(APP-001): replace with Polysil's official logo once the client shares brand assets.
 */
export function BrandMark({ className }: { className?: string }): React.JSX.Element {
  return (
    <svg
      viewBox="0 0 32 32"
      aria-hidden="true"
      className={cn("shrink-0 overflow-hidden rounded-md", className)}
    >
      <rect width="32" height="32" className="fill-primary" />
      <path
        d="M16 7.5c-3.2 4.1-6 7.6-6 11a6 6 0 0 0 12 0c0-3.4-2.8-6.9-6-11Z"
        className="fill-primary-foreground"
      />
      <path
        d="M13.3 19.4a2.8 2.8 0 0 0 2.7 2.5"
        fill="none"
        strokeWidth={1.6}
        strokeLinecap="round"
        className="stroke-primary"
      />
    </svg>
  );
}
