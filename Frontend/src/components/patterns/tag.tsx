"use client";

import type * as React from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { EMPTY_VALUE } from "@/lib/format";
import { cn } from "@/lib/utils";

export const TAG_TONES = [
  "teal",
  "blue",
  "violet",
  "rose",
  "orange",
  "amber",
  "lime",
  "slate",
] as const;

export type TagTone = (typeof TAG_TONES)[number];

const dotClasses: Readonly<Record<TagTone, string>> = {
  teal: "bg-tag-teal",
  blue: "bg-tag-blue",
  violet: "bg-tag-violet",
  rose: "bg-tag-rose",
  orange: "bg-tag-orange",
  amber: "bg-tag-amber",
  lime: "bg-tag-lime",
  slate: "bg-tag-slate",
};

/** The same label always gets the same colour (a crop, a source, a district). */
export function toneForLabel(label: string): TagTone {
  let hash = 0;
  for (const char of label.toLowerCase()) {
    hash = (hash * 31 + char.charCodeAt(0)) % 2_147_483_647;
  }
  return TAG_TONES[hash % TAG_TONES.length] ?? "slate";
}

export interface TagProps extends React.ComponentProps<"span"> {
  tone?: TagTone;
}

/** Categorical label: neutral chip with a coloured dot — calm even when many are on screen. */
export function Tag({
  tone = "slate",
  className,
  children,
  ...props
}: TagProps): React.JSX.Element {
  return (
    <span
      data-slot="tag"
      className={cn(
        "inline-flex h-6 max-w-40 min-w-0 items-center gap-1.5 rounded-sm border border-border bg-card px-1.5 text-xs font-medium text-foreground",
        className,
      )}
      {...props}
    >
      <span aria-hidden="true" className={cn("size-1.5 shrink-0 rounded-full", dotClasses[tone])} />
      <span className="truncate">{children}</span>
    </span>
  );
}

export interface TagItem {
  readonly id: string;
  readonly label: string;
  readonly tone?: TagTone;
}

export interface TagListProps {
  items: readonly TagItem[];
  /** Tags shown before collapsing the rest into "+N". */
  max?: number;
  className?: string;
}

/** Shows up to `max` tags; the rest collapse into a "+N" chip with a tooltip listing them. */
export function TagList({ items, max = 2, className }: TagListProps): React.JSX.Element {
  if (items.length === 0) {
    return <span className="text-sm text-subtle-foreground">{EMPTY_VALUE}</span>;
  }

  const visible = items.slice(0, max);
  const hidden = items.slice(max);
  const hiddenLabels = hidden.map((item) => item.label).join(", ");

  return (
    <span className={cn("flex min-w-0 items-center gap-1", className)}>
      {visible.map((item) => (
        <Tag key={item.id} tone={item.tone ?? toneForLabel(item.label)}>
          {item.label}
        </Tag>
      ))}
      {hidden.length > 0 ? (
        <Tooltip>
          <TooltipTrigger
            type="button"
            aria-label={`${hidden.length} more: ${hiddenLabels}`}
            className="inline-flex h-6 shrink-0 press-scale items-center rounded-sm border border-border bg-muted px-1.5 text-xs font-medium text-muted-foreground tabular-nums hover:text-foreground"
          >
            +{hidden.length}
          </TooltipTrigger>
          <TooltipContent>{hiddenLabels}</TooltipContent>
        </Tooltip>
      ) : null}
    </span>
  );
}
