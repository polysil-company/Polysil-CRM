"use client";

import { Popover as PopoverPrimitive } from "@base-ui/react/popover";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Shared surface for floating panels (popover, menu, select). Scales from the
 * trigger (`--transform-origin`), never from the centre.
 */
export const floatingSurfaceClasses = cn(
  "origin-(--transform-origin) rounded-lg border border-border bg-popover text-popover-foreground shadow-md outline-none",
  "transition-[opacity,scale] duration-base ease-out data-ending-style:scale-96 data-ending-style:opacity-0 data-starting-style:scale-96 data-starting-style:opacity-0",
);

/** Based on shadcn/ui (base-nova) — restyled. */
export const Popover = PopoverPrimitive.Root;

export function PopoverTrigger(props: PopoverPrimitive.Trigger.Props): React.JSX.Element {
  return <PopoverPrimitive.Trigger data-slot="popover-trigger" {...props} />;
}

export interface PopoverContentProps
  extends
    Omit<PopoverPrimitive.Popup.Props, "className">,
    Pick<PopoverPrimitive.Positioner.Props, "align" | "alignOffset" | "side" | "sideOffset"> {
  className?: string;
}

export function PopoverContent({
  className,
  align = "start",
  alignOffset = 0,
  side = "bottom",
  sideOffset = 6,
  ...props
}: PopoverContentProps): React.JSX.Element {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
        className="layer-popover"
      >
        <PopoverPrimitive.Popup
          data-slot="popover-content"
          className={cn(floatingSurfaceClasses, "flex w-72 flex-col gap-3 p-3 text-sm", className)}
          {...props}
        />
      </PopoverPrimitive.Positioner>
    </PopoverPrimitive.Portal>
  );
}

export function PopoverTitle({
  className,
  ...props
}: Omit<PopoverPrimitive.Title.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <PopoverPrimitive.Title
      data-slot="popover-title"
      className={cn("text-sm font-medium text-foreground", className)}
      {...props}
    />
  );
}

export function PopoverDescription({
  className,
  ...props
}: Omit<PopoverPrimitive.Description.Props, "className"> & {
  className?: string;
}): React.JSX.Element {
  return (
    <PopoverPrimitive.Description
      data-slot="popover-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}
