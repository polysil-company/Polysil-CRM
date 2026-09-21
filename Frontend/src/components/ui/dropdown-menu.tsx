"use client";

import { Menu as MenuPrimitive } from "@base-ui/react/menu";
import { ArrowRight01Icon, Tick02Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { cn } from "@/lib/utils";

import { Icon } from "./icon";
import { floatingSurfaceClasses } from "./popover";

/** Based on shadcn/ui (base-nova) — restyled. */
export const DropdownMenu = MenuPrimitive.Root;

export function DropdownMenuTrigger(props: MenuPrimitive.Trigger.Props): React.JSX.Element {
  return <MenuPrimitive.Trigger data-slot="dropdown-menu-trigger" {...props} />;
}

const itemClasses = cn(
  "relative flex cursor-default items-center gap-2 rounded-md px-2 py-1.5 text-sm text-foreground outline-none select-none",
  "data-highlighted:bg-accent data-highlighted:text-accent-foreground",
  "data-disabled:pointer-events-none data-disabled:opacity-50",
  "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground",
);

export interface DropdownMenuContentProps
  extends
    Omit<MenuPrimitive.Popup.Props, "className">,
    Pick<MenuPrimitive.Positioner.Props, "align" | "alignOffset" | "side" | "sideOffset"> {
  className?: string;
}

export function DropdownMenuContent({
  align = "start",
  alignOffset = 0,
  side = "bottom",
  sideOffset = 6,
  className,
  ...props
}: DropdownMenuContentProps): React.JSX.Element {
  return (
    <MenuPrimitive.Portal>
      <MenuPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
        className="layer-popover outline-none"
      >
        <MenuPrimitive.Popup
          data-slot="dropdown-menu-content"
          className={cn(
            floatingSurfaceClasses,
            "max-h-(--available-height) min-w-44 scrollbar-thin overflow-x-hidden overflow-y-auto p-1",
            className,
          )}
          {...props}
        />
      </MenuPrimitive.Positioner>
    </MenuPrimitive.Portal>
  );
}

export const DropdownMenuGroup = MenuPrimitive.Group;

export function DropdownMenuLabel({
  className,
  ...props
}: Omit<MenuPrimitive.GroupLabel.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <MenuPrimitive.GroupLabel
      data-slot="dropdown-menu-label"
      className={cn(
        "px-2 pt-2 pb-1 text-2xs font-medium tracking-wider text-subtle-foreground uppercase",
        className,
      )}
      {...props}
    />
  );
}

export interface DropdownMenuItemProps extends Omit<MenuPrimitive.Item.Props, "className"> {
  className?: string;
  variant?: "default" | "destructive";
}

export function DropdownMenuItem({
  className,
  variant = "default",
  ...props
}: DropdownMenuItemProps): React.JSX.Element {
  return (
    <MenuPrimitive.Item
      data-slot="dropdown-menu-item"
      data-variant={variant}
      className={cn(
        itemClasses,
        "data-[variant=destructive]:text-danger data-[variant=destructive]:data-highlighted:bg-danger-soft data-[variant=destructive]:[&_svg]:text-danger",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuCheckboxItem({
  className,
  children,
  ...props
}: Omit<MenuPrimitive.CheckboxItem.Props, "className"> & {
  className?: string;
}): React.JSX.Element {
  return (
    <MenuPrimitive.CheckboxItem
      data-slot="dropdown-menu-checkbox-item"
      className={cn(itemClasses, "pr-8", className)}
      {...props}
    >
      {children}
      <span className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
        <MenuPrimitive.CheckboxItemIndicator>
          <Icon icon={Tick02Icon} strokeWidth={2} className="text-foreground" />
        </MenuPrimitive.CheckboxItemIndicator>
      </span>
    </MenuPrimitive.CheckboxItem>
  );
}

export const DropdownMenuRadioGroup = MenuPrimitive.RadioGroup;

export function DropdownMenuRadioItem({
  className,
  children,
  ...props
}: Omit<MenuPrimitive.RadioItem.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <MenuPrimitive.RadioItem
      data-slot="dropdown-menu-radio-item"
      className={cn(itemClasses, "pr-8", className)}
      {...props}
    >
      {children}
      <span className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
        <MenuPrimitive.RadioItemIndicator>
          <Icon icon={Tick02Icon} strokeWidth={2} className="text-foreground" />
        </MenuPrimitive.RadioItemIndicator>
      </span>
    </MenuPrimitive.RadioItem>
  );
}

export const DropdownMenuSub = MenuPrimitive.SubmenuRoot;

export function DropdownMenuSubTrigger({
  className,
  children,
  ...props
}: Omit<MenuPrimitive.SubmenuTrigger.Props, "className"> & {
  className?: string;
}): React.JSX.Element {
  return (
    <MenuPrimitive.SubmenuTrigger
      data-slot="dropdown-menu-sub-trigger"
      className={cn(itemClasses, "data-popup-open:bg-accent", className)}
      {...props}
    >
      {children}
      <Icon icon={ArrowRight01Icon} className="ml-auto" />
    </MenuPrimitive.SubmenuTrigger>
  );
}

export function DropdownMenuSeparator({
  className,
  ...props
}: Omit<MenuPrimitive.Separator.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <MenuPrimitive.Separator
      data-slot="dropdown-menu-separator"
      className={cn("-mx-1 my-1 h-px bg-border", className)}
      {...props}
    />
  );
}

export function DropdownMenuShortcut({
  className,
  ...props
}: React.ComponentProps<"span">): React.JSX.Element {
  return (
    <span
      data-slot="dropdown-menu-shortcut"
      className={cn("ml-auto text-xs tracking-wide text-subtle-foreground", className)}
      {...props}
    />
  );
}
