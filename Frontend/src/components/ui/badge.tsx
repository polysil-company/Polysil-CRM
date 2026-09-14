"use client";

import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Based on shadcn/ui (base-nova) — restyled to Polysil tokens.
 * Status pills and counts. For categorical labels use `Tag`.
 */
export const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-full border border-transparent font-medium whitespace-nowrap tabular-nums [&>svg]:pointer-events-none [&>svg]:size-3",
  {
    variants: {
      variant: {
        neutral: "bg-muted text-muted-foreground",
        primary: "bg-primary-soft text-primary-soft-foreground",
        success: "bg-success-soft text-success",
        warning: "bg-warning-soft text-warning",
        danger: "bg-danger-soft text-danger",
        info: "bg-info-soft text-info",
        highlight: "bg-highlight text-highlight-foreground",
        outline: "border-border text-muted-foreground",
      },
      size: {
        sm: "h-5 px-1.5 text-2xs",
        md: "h-6 px-2 text-xs",
      },
    },
    defaultVariants: {
      variant: "neutral",
      size: "md",
    },
  },
);

export type BadgeVariant = NonNullable<VariantProps<typeof badgeVariants>["variant"]>;

const dotClasses: Readonly<Record<BadgeVariant, string>> = {
  neutral: "bg-subtle-foreground",
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
  highlight: "bg-highlight-foreground",
  outline: "bg-subtle-foreground",
};

export interface BadgeProps
  extends useRender.ComponentProps<"span">, VariantProps<typeof badgeVariants> {
  /** Leading status dot in the badge colour. */
  dot?: boolean;
}

export function Badge({
  className,
  variant,
  size,
  dot = false,
  render,
  children,
  ...props
}: BadgeProps): React.ReactElement {
  const dotClass = dotClasses[variant ?? "neutral"];

  return useRender({
    defaultTagName: "span",
    render,
    props: mergeProps<"span">(
      {
        className: cn(badgeVariants({ variant, size }), className),
        children: (
          <>
            {dot ? (
              <span aria-hidden="true" className={cn("size-1.5 rounded-full", dotClass)} />
            ) : null}
            {children}
          </>
        ),
      },
      props,
    ),
    state: { slot: "badge" },
  });
}
