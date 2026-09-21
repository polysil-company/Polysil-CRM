import type * as React from "react";

import { cn } from "@/lib/utils";

/** Based on shadcn/ui (base-nova) — restyled. Keyboard shortcut hint. */
export function Kbd({ className, ...props }: React.ComponentProps<"kbd">): React.JSX.Element {
  return (
    <kbd
      data-slot="kbd"
      className={cn(
        "pointer-events-none inline-flex h-5 min-w-5 items-center justify-center gap-0.5 rounded-xs border border-border bg-muted px-1 font-sans text-2xs font-medium text-muted-foreground select-none",
        "in-data-[slot=tooltip-content]:border-transparent in-data-[slot=tooltip-content]:bg-background/15 in-data-[slot=tooltip-content]:text-background",
        "[&_svg]:size-3",
        className,
      )}
      {...props}
    />
  );
}

export function KbdGroup({ className, ...props }: React.ComponentProps<"kbd">): React.JSX.Element {
  return (
    <kbd
      data-slot="kbd-group"
      className={cn("inline-flex items-center gap-1", className)}
      {...props}
    />
  );
}
