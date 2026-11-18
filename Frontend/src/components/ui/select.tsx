"use client";

import { Select as SelectPrimitive } from "@base-ui/react/select";
import { Tick02Icon, UnfoldMoreIcon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { cn } from "@/lib/utils";

import { Icon } from "./icon";
import { fieldControlClasses } from "./input";
import { floatingSurfaceClasses } from "./popover";

/** Based on shadcn/ui (base-nova) — restyled. Opens below the trigger (not over it). */
export const Select = SelectPrimitive.Root;

export function SelectValue({
  className,
  ...props
}: Omit<SelectPrimitive.Value.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <SelectPrimitive.Value
      data-slot="select-value"
      className={cn("flex flex-1 truncate text-left", className)}
      {...props}
    />
  );
}

export interface SelectTriggerProps extends Omit<SelectPrimitive.Trigger.Props, "className"> {
  className?: string;
  size?: "sm" | "md";
}

export function SelectTrigger({
  className,
  size = "md",
  children,
  ...props
}: SelectTriggerProps): React.JSX.Element {
  return (
    <SelectPrimitive.Trigger
      data-slot="select-trigger"
      data-size={size}
      className={cn(
        fieldControlClasses,
        "flex items-center justify-between gap-2 pr-2 pl-3 whitespace-nowrap select-none",
        "data-[size=md]:h-control-md data-[size=sm]:h-control-sm data-[size=md]:pointer-coarse:h-control-lg",
        "data-placeholder:text-subtle-foreground",
        className,
      )}
      {...props}
    >
      {children}
      <SelectPrimitive.Icon className="flex text-subtle-foreground">
        <Icon icon={UnfoldMoreIcon} />
      </SelectPrimitive.Icon>
    </SelectPrimitive.Trigger>
  );
}

export interface SelectContentProps
  extends
    Omit<SelectPrimitive.Popup.Props, "className">,
    Pick<SelectPrimitive.Positioner.Props, "align" | "alignOffset" | "side" | "sideOffset"> {
  className?: string;
}

export function SelectContent({
  className,
  children,
  side = "bottom",
  sideOffset = 6,
  align = "start",
  alignOffset = 0,
  ...props
}: SelectContentProps): React.JSX.Element {
  return (
    <SelectPrimitive.Portal>
      <SelectPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        alignItemWithTrigger={false}
        className="layer-popover"
      >
        <SelectPrimitive.Popup
          data-slot="select-content"
          className={cn(
            floatingSurfaceClasses,
            "max-h-(--available-height) min-w-(--anchor-width) scrollbar-thin overflow-y-auto p-1",
            className,
          )}
          {...props}
        >
          <SelectPrimitive.List>{children}</SelectPrimitive.List>
        </SelectPrimitive.Popup>
      </SelectPrimitive.Positioner>
    </SelectPrimitive.Portal>
  );
}

export function SelectItem({
  className,
  children,
  ...props
}: Omit<SelectPrimitive.Item.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <SelectPrimitive.Item
      data-slot="select-item"
      className={cn(
        "relative flex w-full cursor-default items-center gap-2 rounded-md py-1.5 pr-8 pl-2 text-sm text-foreground outline-none select-none",
        "data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-accent",
        className,
      )}
      {...props}
    >
      <SelectPrimitive.ItemText className="flex flex-1 gap-2 truncate">
        {children}
      </SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
        <Icon icon={Tick02Icon} strokeWidth={2} />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}

export function SelectGroupLabel({
  className,
  ...props
}: Omit<SelectPrimitive.GroupLabel.Props, "className"> & {
  className?: string;
}): React.JSX.Element {
  return (
    <SelectPrimitive.GroupLabel
      data-slot="select-label"
      className={cn(
        "px-2 pt-2 pb-1 text-2xs font-medium tracking-wider text-subtle-foreground uppercase",
        className,
      )}
      {...props}
    />
  );
}

export const SelectGroup = SelectPrimitive.Group;
