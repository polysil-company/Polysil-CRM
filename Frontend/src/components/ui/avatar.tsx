"use client";

import { Avatar as AvatarPrimitive } from "@base-ui/react/avatar";
import { cva } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

/** Based on shadcn/ui (base-nova) — restyled. Falls back to initials. */
const avatarVariants = cva(
  "relative flex shrink-0 overflow-hidden rounded-full bg-muted font-medium text-muted-foreground select-none after:absolute after:inset-0 after:rounded-full after:border after:border-border",
  {
    variants: {
      size: {
        xs: "size-5 text-2xs",
        sm: "size-6 text-2xs",
        md: "size-8 text-xs",
        lg: "size-10 text-sm",
      },
    },
    defaultVariants: { size: "md" },
  },
);

export interface AvatarProps extends Omit<AvatarPrimitive.Root.Props, "className"> {
  className?: string;
  size?: "xs" | "sm" | "md" | "lg";
}

export function Avatar({ className, size = "md", ...props }: AvatarProps): React.JSX.Element {
  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      data-size={size}
      className={cn(avatarVariants({ size }), className)}
      {...props}
    />
  );
}

export function AvatarImage({
  className,
  ...props
}: Omit<AvatarPrimitive.Image.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <AvatarPrimitive.Image
      data-slot="avatar-image"
      className={cn("aspect-square size-full object-cover", className)}
      {...props}
    />
  );
}

export function AvatarFallback({
  className,
  ...props
}: Omit<AvatarPrimitive.Fallback.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <AvatarPrimitive.Fallback
      data-slot="avatar-fallback"
      className={cn("flex size-full items-center justify-center", className)}
      {...props}
    />
  );
}

/** "Ramesh Patel" → "RP"; "Kiran" → "KI". */
export function getInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return (words[0] ?? "").slice(0, 2).toUpperCase();
  return `${words[0]?.[0] ?? ""}${words.at(-1)?.[0] ?? ""}`.toUpperCase();
}
