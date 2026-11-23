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
  /**
   * The title's heading level: 1 when the state is the whole page (a standalone 404), 2 when it
   * fills a page under the top bar's title, 3 (default) inside a section.
   */
  level?: 1 | 2 | 3;
  className?: string;
}

/** Nothing to show yet — or nothing matches the filters. Always offer a next step. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  level = 3,
  className,
}: EmptyStateProps): React.JSX.Element {
  return (
    <Empty className={className}>
      <EmptyMedia>
        <Icon icon={icon} />
      </EmptyMedia>
      <div className="flex flex-col items-center gap-1">
        <EmptyTitle level={level}>{title}</EmptyTitle>
        {description ? <EmptyDescription>{description}</EmptyDescription> : null}
      </div>
      {action ? <EmptyContent>{action}</EmptyContent> : null}
    </Empty>
  );
}
