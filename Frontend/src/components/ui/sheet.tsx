"use client";

import { Dialog as SheetPrimitive } from "@base-ui/react/dialog";
import { Cancel01Icon } from "@hugeicons/core-free-icons";
import { cva } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

import { Button } from "./button";
import { Icon } from "./icon";

/** Based on shadcn/ui (base-nova) — restyled. Slides from an edge with the drawer curve. */
export const Sheet = SheetPrimitive.Root;

export function SheetTrigger(props: SheetPrimitive.Trigger.Props): React.JSX.Element {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />;
}

export function SheetClose(props: SheetPrimitive.Close.Props): React.JSX.Element {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />;
}

const sheetVariants = cva(
  "fixed layer-modal flex flex-col bg-popover text-popover-foreground shadow-lg transition-[translate] duration-slow ease-drawer outline-none",
  {
    variants: {
      side: {
        left: "inset-y-0 left-0 h-full w-[min(20rem,88vw)] border-r border-border data-ending-style:-translate-x-full data-starting-style:-translate-x-full",
        right:
          "inset-y-0 right-0 h-full w-[min(24rem,92vw)] border-l border-border data-ending-style:translate-x-full data-starting-style:translate-x-full",
        bottom:
          "inset-x-0 bottom-0 max-h-[85dvh] rounded-t-2xl border-t border-border safe-bottom data-ending-style:translate-y-full data-starting-style:translate-y-full",
      },
    },
    defaultVariants: { side: "right" },
  },
);

export interface SheetContentProps extends Omit<SheetPrimitive.Popup.Props, "className"> {
  className?: string;
  side?: "left" | "right" | "bottom";
  showCloseButton?: boolean;
}

export function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  ...props
}: SheetContentProps): React.JSX.Element {
  return (
    <SheetPrimitive.Portal>
      <SheetPrimitive.Backdrop
        data-slot="sheet-overlay"
        className="fixed inset-0 layer-modal bg-overlay transition-opacity duration-slow ease-out data-ending-style:opacity-0 data-starting-style:opacity-0"
      />
      <SheetPrimitive.Popup
        data-slot="sheet-content"
        data-side={side}
        className={cn(sheetVariants({ side }), className)}
        {...props}
      >
        {children}
        {showCloseButton ? (
          <SheetPrimitive.Close
            data-slot="sheet-close"
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                className="absolute top-3 right-3"
                aria-label="Close"
              />
            }
          >
            <Icon icon={Cancel01Icon} />
          </SheetPrimitive.Close>
        ) : null}
      </SheetPrimitive.Popup>
    </SheetPrimitive.Portal>
  );
}

export function SheetHeader({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="sheet-header"
      className={cn("flex flex-col gap-1 p-4 pr-12", className)}
      {...props}
    />
  );
}

export function SheetTitle({
  className,
  ...props
}: Omit<SheetPrimitive.Title.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cn("text-lg font-semibold text-foreground", className)}
      {...props}
    />
  );
}

export function SheetDescription({
  className,
  ...props
}: Omit<SheetPrimitive.Description.Props, "className"> & {
  className?: string;
}): React.JSX.Element {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}
