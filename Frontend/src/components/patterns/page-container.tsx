import type * as React from "react";

import { cn } from "@/lib/utils";

export interface PageContainerProps extends React.ComponentProps<"div"> {
  /** Fill the panel height so a table scrolls inside its own area (desktop). */
  fill?: boolean;
}

/** Standard page padding and vertical rhythm. Every page renders inside one. */
export function PageContainer({
  fill = false,
  className,
  ...props
}: PageContainerProps): React.JSX.Element {
  return (
    <div
      data-slot="page-container"
      className={cn(
        "flex w-full flex-col gap-5 px-4 py-5 sm:px-6 lg:px-8 lg:py-6",
        fill && "lg:h-full lg:min-h-0",
        className,
      )}
      {...props}
    />
  );
}
