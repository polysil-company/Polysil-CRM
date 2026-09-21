"use client";

import { Separator as SeparatorPrimitive } from "@base-ui/react/separator";
import type * as React from "react";

import { cn } from "@/lib/utils";

export interface SeparatorProps extends Omit<SeparatorPrimitive.Props, "className"> {
  className?: string;
}

/** Based on shadcn/ui (base-nova). */
export function Separator({
  className,
  orientation = "horizontal",
  ...props
}: SeparatorProps): React.JSX.Element {
  return (
    <SeparatorPrimitive
      data-slot="separator"
      orientation={orientation}
      className={cn(
        "shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:w-px data-[orientation=vertical]:self-stretch",
        className,
      )}
      {...props}
    />
  );
}
