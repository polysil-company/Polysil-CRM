import type * as React from "react";

import { cn } from "@/lib/utils";

import { fieldControlClasses } from "./input";

export type TextareaProps = React.ComponentProps<"textarea">;

/** Based on shadcn/ui (base-nova) — restyled. Grows with its content. */
export function Textarea({ className, ...props }: TextareaProps): React.JSX.Element {
  return (
    <textarea
      data-slot="textarea"
      className={cn(fieldControlClasses, "field-sizing-content min-h-20 px-3 py-2", className)}
      {...props}
    />
  );
}
