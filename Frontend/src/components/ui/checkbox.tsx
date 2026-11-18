"use client";

import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";
import { MinusSignIcon, Tick02Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { cn } from "@/lib/utils";

import { Icon } from "./icon";

/**
 * Based on shadcn/ui (base-nova) — restyled. Checked uses the "sun"
 * highlight, matching table row selection. Hit area extends beyond the
 * 16px box for touch.
 */
export interface CheckboxProps extends Omit<CheckboxPrimitive.Root.Props, "className"> {
  className?: string;
}

export function Checkbox({ className, ...props }: CheckboxProps): React.JSX.Element {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "group/checkbox peer relative flex size-4 shrink-0 items-center justify-center rounded-xs border border-control bg-card text-highlight-foreground transition-colors duration-fast",
        "after:absolute after:-inset-2",
        "hover:border-foreground/60",
        "data-checked:border-highlight-border data-checked:bg-highlight data-indeterminate:border-highlight-border data-indeterminate:bg-highlight",
        "aria-invalid:border-danger",
        "data-disabled:cursor-not-allowed data-disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center transition-[opacity,scale] duration-press ease-out data-starting-style:scale-75 data-starting-style:opacity-0"
      >
        <Icon
          icon={Tick02Icon}
          strokeWidth={2}
          size="xs"
          className="group-data-indeterminate/checkbox:hidden"
        />
        <Icon
          icon={MinusSignIcon}
          strokeWidth={2}
          size="xs"
          className="hidden group-data-indeterminate/checkbox:block"
        />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
