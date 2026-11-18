"use client";

import { Radio as RadioPrimitive } from "@base-ui/react/radio";
import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Based on shadcn/ui (base-nova) — restyled to match Checkbox: the chosen option uses the
 * "sun" highlight. Arrow keys move between options; the hit area extends beyond the dot.
 *
 *   <RadioGroup value={value} onValueChange={setValue} aria-label="Inquiry type">
 *     <label><RadioGroupItem value="commercial" /> Commercial</label>
 *   </RadioGroup>
 */
export function RadioGroup<TValue>({
  className,
  ...props
}: Omit<RadioGroupPrimitive.Props<TValue>, "className"> & {
  className?: string;
}): React.JSX.Element {
  return (
    <RadioGroupPrimitive
      data-slot="radio-group"
      className={cn("flex flex-col gap-2", className)}
      {...props}
    />
  );
}

export interface RadioGroupItemProps extends Omit<RadioPrimitive.Root.Props, "className"> {
  className?: string;
}

export function RadioGroupItem({ className, ...props }: RadioGroupItemProps): React.JSX.Element {
  return (
    <RadioPrimitive.Root
      data-slot="radio-group-item"
      className={cn(
        "relative flex size-4 shrink-0 items-center justify-center rounded-full border border-control bg-card transition-colors duration-fast",
        "after:absolute after:-inset-2",
        "hover:border-foreground/60",
        "data-checked:border-highlight-border data-checked:bg-highlight",
        "aria-invalid:border-danger",
        "data-disabled:cursor-not-allowed data-disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <RadioPrimitive.Indicator
        data-slot="radio-group-indicator"
        className="size-1.5 rounded-full bg-highlight-foreground transition-[opacity,scale] duration-press ease-out data-starting-style:scale-75 data-starting-style:opacity-0"
      />
    </RadioPrimitive.Root>
  );
}
