"use client";

import { Toggle as TogglePrimitive } from "@base-ui/react/toggle";
import { ToggleGroup as ToggleGroupPrimitive } from "@base-ui/react/toggle-group";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Based on shadcn/ui (base-nova) — restyled; the inline `--gap` style is
 * replaced by a fixed segmented look. Use for small exclusive choices
 * (view mode, density, date range presets).
 */
export function ToggleGroup({
  className,
  ...props
}: Omit<ToggleGroupPrimitive.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <ToggleGroupPrimitive
      data-slot="toggle-group"
      className={cn("inline-flex w-fit items-center gap-0.5 rounded-md bg-muted p-0.5", className)}
      {...props}
    />
  );
}

export function ToggleGroupItem({
  className,
  ...props
}: Omit<TogglePrimitive.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <TogglePrimitive
      data-slot="toggle-group-item"
      className={cn(
        "inline-flex h-control-sm press-scale items-center justify-center gap-1.5 rounded-sm px-2.5 text-sm font-medium text-muted-foreground select-none",
        "hover:text-foreground data-pressed:bg-card data-pressed:text-foreground data-pressed:shadow-xs",
        "data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:size-4",
        className,
      )}
      {...props}
    />
  );
}
