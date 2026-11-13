import type * as React from "react";

import { cn } from "@/lib/utils";

import { fieldControlClasses } from "./input";

/**
 * Based on shadcn/ui (base-nova) — simplified. An input with leading/trailing
 * adornments (icon, shortcut hint, clear button) inside one field border.
 *
 *   <InputGroup>
 *     <InputGroupAddon><Icon icon={Search01Icon} /></InputGroupAddon>
 *     <InputGroupInput placeholder="Search leads" aria-label="Search leads" />
 *     <InputGroupAddon align="end"><Kbd>/</Kbd></InputGroupAddon>
 *   </InputGroup>
 */
export function InputGroup({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="input-group"
      className={cn(
        fieldControlClasses,
        "relative flex h-control-md items-center gap-2 px-2.5 pointer-coarse:h-control-lg",
        "has-[input:focus-visible]:border-ring has-[input:focus-visible]:outline-2 has-[input:focus-visible]:outline-offset-0 has-[input:focus-visible]:outline-ring/30 has-[input:focus-visible]:outline-solid",
        "has-[input[aria-invalid=true]]:border-danger",
        className,
      )}
      {...props}
    />
  );
}

export function InputGroupAddon({
  className,
  align = "start",
  ...props
}: React.ComponentProps<"div"> & { align?: "start" | "end" }): React.JSX.Element {
  return (
    <div
      data-slot="input-group-addon"
      data-align={align}
      className={cn(
        "flex shrink-0 items-center gap-1.5 text-subtle-foreground [&_svg]:size-4",
        align === "start" ? "order-first" : "order-last",
        className,
      )}
      {...props}
    />
  );
}

export function InputGroupInput({
  className,
  ...props
}: React.ComponentProps<"input">): React.JSX.Element {
  return (
    <input
      data-slot="input-group-control"
      className={cn(
        "h-full min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-subtle-foreground focus-visible:outline-none pointer-coarse:text-md",
        className,
      )}
      {...props}
    />
  );
}
