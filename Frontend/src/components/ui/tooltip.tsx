"use client";

import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Based on shadcn/ui (base-nova) — restyled.
 * First tooltip waits 400ms; moving to a neighbour opens it instantly with no
 * animation (`data-instant`), so toolbars feel fast.
 */
export function TooltipProvider({
  delay = 400,
  closeDelay = 0,
  ...props
}: TooltipPrimitive.Provider.Props): React.JSX.Element {
  return <TooltipPrimitive.Provider delay={delay} closeDelay={closeDelay} {...props} />;
}

export const Tooltip = TooltipPrimitive.Root;

export function TooltipTrigger(props: TooltipPrimitive.Trigger.Props): React.JSX.Element {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

export interface TooltipContentProps
  extends
    Omit<TooltipPrimitive.Popup.Props, "className">,
    Pick<TooltipPrimitive.Positioner.Props, "align" | "alignOffset" | "side" | "sideOffset"> {
  className?: string;
}

export function TooltipContent({
  className,
  side = "top",
  sideOffset = 6,
  align = "center",
  alignOffset = 0,
  ...props
}: TooltipContentProps): React.JSX.Element {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        className="layer-tooltip"
      >
        <TooltipPrimitive.Popup
          data-slot="tooltip-content"
          className={cn(
            "inline-flex max-w-xs origin-(--transform-origin) items-center gap-1.5 rounded-sm bg-foreground px-2 py-1 text-xs text-background shadow-md",
            "transition-[opacity,scale] duration-fast ease-out data-ending-style:scale-97 data-ending-style:opacity-0 data-starting-style:scale-97 data-starting-style:opacity-0",
            "data-instant:duration-instant",
            className,
          )}
          {...props}
        />
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  );
}
