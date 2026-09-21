"use client";

import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Icon, type IconGlyph } from "@/components/ui/icon";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface FilterOption<TValue extends string> {
  readonly value: TValue;
  readonly label: string;
  /** Matching records, when the API provides counts. */
  readonly count?: number | undefined;
}

export interface FilterPillProps<TValue extends string> {
  label: string;
  options: readonly FilterOption<TValue>[];
  selected: readonly TValue[];
  onChange: (next: TValue[]) => void;
  icon?: IconGlyph;
  className?: string;
}

/**
 * A multi-select filter as a pill. Dashed when unset; solid with a summary
 * when set. State belongs in the URL (nuqs) so a filtered view can be shared.
 */
export function FilterPill<TValue extends string>({
  label,
  options,
  selected,
  onChange,
  icon,
  className,
}: FilterPillProps<TValue>): React.JSX.Element {
  const active = selected.length > 0;
  const firstSelected = options.find((option) => option.value === selected[0]);
  const summary = !active
    ? undefined
    : selected.length === 1 && firstSelected
      ? firstSelected.label
      : `${selected.length} selected`;

  const toggle = (value: TValue, checked: boolean): void => {
    onChange(checked ? [...selected, value] : selected.filter((item) => item !== value));
  };

  return (
    <Popover>
      <PopoverTrigger
        className={cn(
          "inline-flex h-control-sm press-scale items-center gap-1.5 rounded-full border px-3 text-sm font-medium whitespace-nowrap",
          active
            ? "border-border-strong bg-accent text-foreground"
            : "border-dashed border-border-strong text-muted-foreground hover:bg-accent hover:text-foreground",
          className,
        )}
      >
        {icon ? <Icon icon={icon} size="sm" /> : null}
        <span>{label}</span>
        {summary ? (
          <>
            <span aria-hidden="true" className="h-3.5 w-px bg-border-strong" />
            <span className="max-w-32 truncate text-foreground">{summary}</span>
          </>
        ) : null}
      </PopoverTrigger>
      <PopoverContent className="w-60 gap-0 p-1">
        <div role="group" aria-label={`Filter by ${label.toLowerCase()}`} className="flex flex-col">
          {options.map((option) => (
            <label
              key={option.value}
              className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-foreground hover:bg-accent"
            >
              <Checkbox
                checked={selected.includes(option.value)}
                onCheckedChange={(checked) => {
                  toggle(option.value, checked);
                }}
              />
              <span className="flex-1 truncate">{option.label}</span>
              {option.count === undefined ? null : (
                <span className="text-xs text-subtle-foreground tabular-nums">
                  {formatNumber(option.count)}
                </span>
              )}
            </label>
          ))}
        </div>
        {active ? (
          <>
            <Separator className="my-1" />
            <Button
              variant="ghost"
              size="sm"
              className="w-full"
              onClick={() => {
                onChange([]);
              }}
            >
              Clear {label.toLowerCase()}
            </Button>
          </>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
