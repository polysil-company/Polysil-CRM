import { Input as InputPrimitive } from "@base-ui/react/input";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Shared field chrome for Input, Textarea and Select trigger.
 * 16px text on touch devices prevents iOS Safari from zooming on focus.
 */
export const fieldControlClasses = cn(
  "w-full min-w-0 rounded-md border border-input bg-card text-sm text-foreground shadow-xs transition-[border-color,box-shadow] duration-fast",
  "pointer-coarse:text-md",
  "placeholder:text-subtle-foreground",
  "hover:border-border-strong",
  "focus-visible:border-ring focus-visible:outline-offset-0 focus-visible:outline-ring/30",
  "aria-invalid:border-danger aria-invalid:focus-visible:outline-danger/30",
  "disabled:cursor-not-allowed disabled:opacity-50 data-disabled:cursor-not-allowed data-disabled:opacity-50",
);

export type InputProps = React.ComponentProps<"input">;

/** Based on shadcn/ui (base-nova) — restyled to Polysil tokens. */
export function Input({ className, type = "text", ...props }: InputProps): React.JSX.Element {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        fieldControlClasses,
        "h-control-md px-3 pointer-coarse:h-control-lg",
        "file:mr-2 file:h-full file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-foreground",
        className,
      )}
      {...props}
    />
  );
}
