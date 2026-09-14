"use client";

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
import { Cancel01Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { cn } from "@/lib/utils";

import { Button } from "./button";
import { Icon } from "./icon";

/**
 * Based on shadcn/ui (base-nova) — restyled.
 * Desktop: centred, scales in from 95%. Phone: a bottom sheet that slides up
 * with the drawer curve. `motion="none"` for high-frequency dialogs such as
 * the command menu (Emil: never animate what people open 100 times a day).
 */
export const Dialog = DialogPrimitive.Root;

export function DialogTrigger(props: DialogPrimitive.Trigger.Props): React.JSX.Element {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

export function DialogClose(props: DialogPrimitive.Close.Props): React.JSX.Element {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

const WIDTH_CLASS = {
  sm: "sm:max-w-sm",
  md: "sm:max-w-lg",
  lg: "sm:max-w-2xl",
} as const;

export interface DialogContentProps extends Omit<DialogPrimitive.Popup.Props, "className"> {
  className?: string;
  size?: keyof typeof WIDTH_CLASS;
  showCloseButton?: boolean;
  motion?: "default" | "none";
}

export function DialogContent({
  className,
  children,
  size = "md",
  showCloseButton = true,
  motion = "default",
  ...props
}: DialogContentProps): React.JSX.Element {
  const animated = motion === "default";

  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Backdrop
        data-slot="dialog-overlay"
        className={cn(
          "fixed inset-0 layer-modal bg-overlay supports-backdrop-filter:backdrop-blur-2xs",
          animated &&
            "transition-opacity duration-slow ease-out data-ending-style:opacity-0 data-starting-style:opacity-0",
        )}
      />
      <DialogPrimitive.Popup
        data-slot="dialog-content"
        className={cn(
          // Phone: bottom sheet
          "fixed inset-x-0 bottom-0 layer-modal flex max-h-[calc(100dvh-1.5rem)] w-full flex-col overflow-hidden rounded-t-2xl border border-border bg-popover text-popover-foreground shadow-lg outline-none max-sm:safe-bottom",
          // Tablet and up: centred dialog
          "sm:inset-x-auto sm:top-1/2 sm:bottom-auto sm:left-1/2 sm:max-h-[calc(100dvh-4rem)] sm:w-[calc(100%-2rem)] sm:-translate-1/2 sm:rounded-xl",
          WIDTH_CLASS[size],
          animated && [
            "transition-[opacity,translate,scale] duration-slow ease-drawer sm:duration-base sm:ease-out",
            "max-sm:data-ending-style:translate-y-full max-sm:data-starting-style:translate-y-full",
            "sm:data-ending-style:scale-95 sm:data-ending-style:opacity-0 sm:data-starting-style:scale-95 sm:data-starting-style:opacity-0",
          ],
          className,
        )}
        {...props}
      >
        {children}
        {showCloseButton ? (
          <DialogPrimitive.Close
            data-slot="dialog-close"
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                className="absolute top-3.5 right-3.5"
                aria-label="Close"
              />
            }
          >
            <Icon icon={Cancel01Icon} />
          </DialogPrimitive.Close>
        ) : null}
      </DialogPrimitive.Popup>
    </DialogPrimitive.Portal>
  );
}

export function DialogHeader({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex flex-col gap-1 px-5 pt-5 pr-14 pb-3", className)}
      {...props}
    />
  );
}

export function DialogBody({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="dialog-body"
      className={cn("flex-1 scrollbar-thin overflow-y-auto px-5 py-2", className)}
      {...props}
    />
  );
}

export function DialogFooter({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "mt-3 flex flex-col-reverse gap-2 border-t border-border bg-muted px-5 py-3.5 sm:flex-row sm:justify-end",
        className,
      )}
      {...props}
    />
  );
}

export function DialogTitle({
  className,
  ...props
}: Omit<DialogPrimitive.Title.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={cn("text-lg font-semibold text-foreground", className)}
      {...props}
    />
  );
}

export function DialogDescription({
  className,
  ...props
}: Omit<DialogPrimitive.Description.Props, "className"> & {
  className?: string;
}): React.JSX.Element {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}
