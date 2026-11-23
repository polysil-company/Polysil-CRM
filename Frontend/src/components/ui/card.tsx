import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * Based on shadcn/ui (base-nova) — restyled. A surface for grouped content:
 * radius xl, hairline border, faint elevation.
 */
export function Card({ className, ...props }: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="card"
      className={cn(
        "flex flex-col rounded-xl border border-border bg-card text-card-foreground shadow-xs",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="card-header"
      className={cn("flex items-start justify-between gap-3 px-5 pt-4 pb-3", className)}
      {...props}
    />
  );
}

export interface CardTitleProps extends React.ComponentProps<"h2"> {
  /** Heading level in the page outline. Cards directly under the page title are level 2. */
  level?: 2 | 3;
}

export function CardTitle({ level = 2, className, ...props }: CardTitleProps): React.JSX.Element {
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <Heading
      data-slot="card-title"
      className={cn("text-base font-semibold text-foreground", className)}
      {...props}
    />
  );
}

export function CardDescription({
  className,
  ...props
}: React.ComponentProps<"p">): React.JSX.Element {
  return (
    <p
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  );
}

export function CardContent({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return <div data-slot="card-content" className={cn("px-5 pb-4", className)} {...props} />;
}

export function CardFooter({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="card-footer"
      className={cn("flex items-center gap-2 border-t border-border px-5 py-3", className)}
      {...props}
    />
  );
}
