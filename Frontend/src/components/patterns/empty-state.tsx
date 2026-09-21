import type * as React from "react";

import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";
import { Icon, type IconGlyph } from "@/components/ui/icon";

export interface EmptyStateProps {
  icon: IconGlyph;
  title: string;
  /** Say why it is empty and what to do next. */
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

/** Nothing to show yet — or nothing matches the filters. Always offer a next step. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps): React.JSX.Element {
  return (
    <Empty className={className}>
      <EmptyMedia>
        <Icon icon={icon} />
      </EmptyMedia>
      <div className="flex flex-col items-center gap-1">
        <EmptyTitle>{title}</EmptyTitle>
        {description ? <EmptyDescription>{description}</EmptyDescription> : null}
      </div>
      {action ? <EmptyContent>{action}</EmptyContent> : null}
    </Empty>
  );
}
