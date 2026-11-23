import { Alert01Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { cn } from "@/lib/utils";

import { Icon } from "./icon";
import { Label } from "./label";

/**
 * Based on shadcn/ui (base-nova) — restyled and simplified.
 *
 *   <Field data-invalid={!!error}>
 *     <FieldLabel htmlFor="phone">Phone</FieldLabel>
 *     <Input id="phone" aria-invalid={!!error} aria-describedby="phone-error" />
 *     <FieldError id="phone-error">{error}</FieldError>
 *   </Field>
 */

export function FieldGroup({
  className,
  ...props
}: React.ComponentProps<"div">): React.JSX.Element {
  return (
    <div
      data-slot="field-group"
      className={cn("flex w-full flex-col gap-4", className)}
      {...props}
    />
  );
}

export function FieldSet({
  className,
  ...props
}: React.ComponentProps<"fieldset">): React.JSX.Element {
  return (
    <fieldset data-slot="field-set" className={cn("flex flex-col gap-3", className)} {...props} />
  );
}

export function FieldLegend({
  className,
  ...props
}: React.ComponentProps<"legend">): React.JSX.Element {
  return (
    <legend
      data-slot="field-legend"
      className={cn("mb-1 text-sm font-medium text-foreground", className)}
      {...props}
    />
  );
}

export interface FieldProps extends React.ComponentProps<"div"> {
  orientation?: "vertical" | "horizontal";
}

export function Field({
  className,
  orientation = "vertical",
  ...props
}: FieldProps): React.JSX.Element {
  return (
    <div
      role="group"
      data-slot="field"
      data-orientation={orientation}
      className={cn(
        "group/field flex w-full gap-1.5",
        orientation === "vertical" ? "flex-col" : "flex-row items-center gap-3",
        className,
      )}
      {...props}
    />
  );
}

export function FieldLabel({
  className,
  ...props
}: React.ComponentProps<typeof Label>): React.JSX.Element {
  return <Label data-slot="field-label" className={cn("w-fit", className)} {...props} />;
}

export function FieldDescription({
  className,
  ...props
}: React.ComponentProps<"p">): React.JSX.Element {
  return (
    <p
      data-slot="field-description"
      className={cn("text-xs/normal text-muted-foreground", className)}
      {...props}
    />
  );
}

export function FieldError({
  className,
  children,
  ...props
}: React.ComponentProps<"p">): React.JSX.Element | null {
  if (children === undefined || children === null || children === false || children === "") {
    return null;
  }
  return (
    <p
      role="alert"
      data-slot="field-error"
      className={cn("flex items-start gap-1.5 text-xs/normal text-danger", className)}
      {...props}
    >
      <Icon icon={Alert01Icon} size="sm" className="mt-px" />
      <span>{children}</span>
    </p>
  );
}
