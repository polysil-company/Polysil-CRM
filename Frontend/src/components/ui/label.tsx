import type * as React from "react";

import { cn } from "@/lib/utils";

export type LabelProps = React.ComponentProps<"label">;

/** Based on shadcn/ui (base-nova) — restyled. Always pair with a control via htmlFor or nesting. */
export function Label({ className, ...props }: LabelProps): React.JSX.Element {
  return (
    // eslint-disable-next-line jsx-a11y/label-has-associated-control -- Generic wrapper: htmlFor or a nested control is supplied at each call site.
    <label
      data-slot="label"
      className={cn(
        "flex items-center gap-2 text-sm/snug font-medium text-foreground select-none",
        "group-data-[disabled=true]/field:opacity-50 peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
