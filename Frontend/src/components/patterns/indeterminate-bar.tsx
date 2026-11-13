import type * as React from "react";

import { cn } from "@/lib/utils";

export interface IndeterminateBarProps {
  active: boolean;
  /** Announced to screen readers while active, e.g. "Updating leads". */
  label: string;
  className?: string;
}

/**
 * Thin progress line for background work such as refetching a table. The
 * content underneath stays visible — never replace loaded data with a skeleton.
 */
export function IndeterminateBar({
  active,
  label,
  className,
}: IndeterminateBarProps): React.JSX.Element {
  return (
    <div
      aria-hidden={!active}
      className={cn(
        "pointer-events-none h-0.5 overflow-hidden transition-opacity duration-base",
        active ? "opacity-100" : "opacity-0",
        className,
      )}
    >
      {active ? (
        <div
          role="progressbar"
          aria-label={label}
          className="h-full w-2/5 animate-indeterminate rounded-full bg-primary"
        />
      ) : null}
    </div>
  );
}
