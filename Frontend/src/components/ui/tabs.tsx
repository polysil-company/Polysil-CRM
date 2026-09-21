"use client";

import { Tabs as TabsPrimitive } from "@base-ui/react/tabs";
import { cva } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Based on shadcn/ui (base-nova) — rebuilt around Base UI's Tabs.Indicator,
 * which slides between tabs using CSS variables (no JS animation).
 * For tabs that change the URL, use `NavTabs` instead.
 */

type TabsVariant = "underline" | "segmented";

export const Tabs = TabsPrimitive.Root;

const listVariants = cva("relative flex items-center", {
  variants: {
    variant: {
      underline: "gap-5 border-b border-border",
      segmented: "inline-flex w-fit gap-0.5 rounded-md bg-muted p-0.5",
    },
  },
});

const tabVariants = cva(
  "relative inline-flex items-center justify-center gap-1.5 text-sm font-medium whitespace-nowrap text-muted-foreground transition-colors duration-fast outline-none select-none hover:text-foreground data-active:text-foreground data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:size-4",
  {
    variants: {
      variant: {
        underline: "h-control-md focus-ring-inset",
        segmented: "h-control-sm rounded-sm px-3 focus-ring-inset",
      },
    },
  },
);

const indicatorVariants = cva(
  "absolute left-0 translate-x-(--active-tab-left) transition-[translate,width] duration-base ease-in-out",
  {
    variants: {
      variant: {
        underline: "-bottom-px h-0.5 w-(--active-tab-width) rounded-full bg-foreground",
        segmented:
          "top-(--active-tab-top) h-(--active-tab-height) w-(--active-tab-width) rounded-sm bg-card shadow-xs",
      },
    },
  },
);

export interface TabsListProps extends Omit<TabsPrimitive.List.Props, "className"> {
  className?: string;
  variant?: TabsVariant;
}

export function TabsList({
  className,
  variant = "underline",
  children,
  ...props
}: TabsListProps): React.JSX.Element {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      data-variant={variant}
      className={cn(listVariants({ variant }), className)}
      {...props}
    >
      <TabsPrimitive.Indicator className={indicatorVariants({ variant })} />
      {children}
    </TabsPrimitive.List>
  );
}

export interface TabsTriggerProps extends Omit<TabsPrimitive.Tab.Props, "className"> {
  className?: string;
  variant?: TabsVariant;
}

export function TabsTrigger({
  className,
  variant = "underline",
  ...props
}: TabsTriggerProps): React.JSX.Element {
  return (
    <TabsPrimitive.Tab
      data-slot="tabs-trigger"
      className={cn(tabVariants({ variant }), className)}
      {...props}
    />
  );
}

export function TabsContent({
  className,
  ...props
}: Omit<TabsPrimitive.Panel.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <TabsPrimitive.Panel
      data-slot="tabs-content"
      className={cn("pt-4 outline-none", className)}
      {...props}
    />
  );
}
