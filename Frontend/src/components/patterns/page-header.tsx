import type * as React from "react";

import { cn } from "@/lib/utils";

export interface PageHeaderProps {
  title: string;
  description?: React.ReactNode;
  /** Beside the title: a status pill, a count. */
  meta?: React.ReactNode;
  /** Right side on desktop, below the title on phones. */
  actions?: React.ReactNode;
  /** Below the header: tabs, filters. */
  children?: React.ReactNode;
  className?: string;
}

/** The one page header. Every page uses it so titles, spacing and actions line up. */
export function PageHeader({
  title,
  description,
  meta,
  actions,
  children,
  className,
}: PageHeaderProps): React.JSX.Element {
  return (
    <header className={cn("flex flex-col gap-4", className)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h1 className="truncate text-xl font-semibold text-foreground">{title}</h1>
            {meta}
          </div>
          {description ? <p className="text-sm text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
      {children}
    </header>
  );
}
