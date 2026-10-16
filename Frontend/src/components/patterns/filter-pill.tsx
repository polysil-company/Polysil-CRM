"use client";

import { useId } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Icon, type IconGlyph } from "@/components/ui/icon";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Separator } from "@/components/ui/separator";
import { formatNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface FilterOption<TValue extends string> {
  readonly value: TValue;
  readonly label: string;
  /** Matching records, when the API provides counts. */
  readonly count?: number | undefined;
  /** One line under the label saying what the option means, for people new to the terms. */
  readonly description?: string | undefined;
}

/** One option row; at least 44px tall on touch screens. Rows with a description align to the top. */
export const filterOptionRowClasses =
  "flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-foreground hover:bg-accent pointer-coarse:min-h-control-lg has-data-[slot=option-description]:items-start";

function hasDescriptions<TValue extends string>(options: readonly FilterOption<TValue>[]): boolean {
  return options.some((option) => option.description !== undefined);
}

/** Ids that tie an option's control to its label and description. */
interface OptionIds {
  readonly label: string;
  readonly description: string;
}

function optionIds(prefix: string, index: number): OptionIds {
  return {
    label: `${prefix}-${String(index)}-label`,
    description: `${prefix}-${String(index)}-description`,
  };
}

/**
 * With a description, the control is named by the label alone and described by the line under
 * it, so a screen reader says "Merged, checkbox" and then what merged means.
 */
function optionAria<TValue extends string>(
  option: FilterOption<TValue>,
  ids: OptionIds,
): { "aria-labelledby"?: string; "aria-describedby"?: string } {
  return option.description === undefined
    ? {}
    : { "aria-labelledby": ids.label, "aria-describedby": ids.description };
}

interface FilterPillBaseProps<TValue extends string> {
  label: string;
  options: readonly FilterOption<TValue>[];
  icon?: IconGlyph;
  /** Shown instead of the options when there are none — e.g. while they load, or if they failed. */
  emptyMessage?: string;
  className?: string;
}

export interface FilterPillProps<TValue extends string> extends FilterPillBaseProps<TValue> {
  selected: readonly TValue[];
  onChange: (next: TValue[]) => void;
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
  emptyMessage,
  className,
}: FilterPillProps<TValue>): React.JSX.Element {
  const firstSelected = options.find((option) => option.value === selected[0]);
  const summary =
    selected.length === 0
      ? undefined
      : selected.length === 1 && firstSelected
        ? firstSelected.label
        : `${selected.length} selected`;

  const idPrefix = useId();
  const toggle = (value: TValue, checked: boolean): void => {
    onChange(checked ? [...selected, value] : selected.filter((item) => item !== value));
  };

  return (
    <FilterPillFrame
      label={label}
      icon={icon}
      summary={summary}
      className={className}
      wide={hasDescriptions(options)}
      onClear={() => {
        onChange([]);
      }}
    >
      {options.length === 0 ? (
        <FilterPillMessage message={emptyMessage} />
      ) : (
        <div role="group" aria-label={`Filter by ${label.toLowerCase()}`} className="flex flex-col">
          {options.map((option, index) => {
            const ids = optionIds(idPrefix, index);
            return (
              <label key={option.value} className={filterOptionRowClasses}>
                <Checkbox
                  className={cn(option.description !== undefined && "mt-0.5")}
                  checked={selected.includes(option.value)}
                  onCheckedChange={(checked) => {
                    toggle(option.value, checked);
                  }}
                  {...optionAria(option, ids)}
                />
                <OptionText option={option} ids={ids} />
              </label>
            );
          })}
        </div>
      )}
    </FilterPillFrame>
  );
}

export interface SingleFilterPillProps<TValue extends string> extends FilterPillBaseProps<TValue> {
  selected: TValue | null;
  onChange: (next: TValue | null) => void;
}

/**
 * A single-choice filter as a pill, for filters the API takes one value of. Same look as
 * FilterPill; the options are radios, so arrow keys move between them.
 */
export function SingleFilterPill<TValue extends string>({
  label,
  options,
  selected,
  onChange,
  icon,
  emptyMessage,
  className,
}: SingleFilterPillProps<TValue>): React.JSX.Element {
  const idPrefix = useId();
  const selectedOption = options.find((option) => option.value === selected);
  // A value the options no longer offer still reads as set, so the pill never hides a filter.
  const summary = selected === null ? undefined : (selectedOption?.label ?? selected);

  return (
    <FilterPillFrame
      label={label}
      icon={icon}
      summary={summary}
      className={className}
      wide={hasDescriptions(options)}
      onClear={() => {
        onChange(null);
      }}
    >
      {options.length === 0 ? (
        <FilterPillMessage message={emptyMessage} />
      ) : (
        <RadioGroup<TValue | null>
          aria-label={`Filter by ${label.toLowerCase()}`}
          value={selected}
          onValueChange={(value) => {
            onChange(value);
          }}
          className="gap-0"
        >
          {options.map((option, index) => {
            const ids = optionIds(idPrefix, index);
            return (
              <label key={option.value} className={filterOptionRowClasses}>
                <RadioGroupItem
                  value={option.value}
                  className={cn(option.description !== undefined && "mt-0.5")}
                  {...optionAria(option, ids)}
                />
                <OptionText option={option} ids={ids} />
              </label>
            );
          })}
        </RadioGroup>
      )}
    </FilterPillFrame>
  );
}

function OptionText<TValue extends string>({
  option,
  ids,
}: {
  option: FilterOption<TValue>;
  ids: OptionIds;
}): React.JSX.Element {
  return (
    <>
      {option.description === undefined ? (
        <span className="flex-1 truncate">{option.label}</span>
      ) : (
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span id={ids.label} className="truncate">
            {option.label}
          </span>
          <span
            id={ids.description}
            data-slot="option-description"
            className="text-xs text-pretty text-muted-foreground"
          >
            {option.description}
          </span>
        </span>
      )}
      {option.count === undefined ? null : (
        <span className="text-xs text-subtle-foreground tabular-nums">
          {formatNumber(option.count)}
        </span>
      )}
    </>
  );
}

function FilterPillMessage({ message }: { message: string | undefined }): React.JSX.Element {
  return <p className="px-2 py-1.5 text-sm text-muted-foreground">{message ?? "No options."}</p>;
}

/**
 * The pill trigger, its popover and the "Clear" action — shared by every kind of pill, including
 * feature pills with their own popover body (the leads area picker).
 */
export function FilterPillFrame({
  label,
  icon,
  summary,
  className,
  wide,
  onClear,
  children,
}: {
  label: string;
  icon: IconGlyph | undefined;
  summary: string | undefined;
  className: string | undefined;
  /** Options carry descriptions: a wider popover that scrolls when the screen is short. */
  wide: boolean;
  onClear: () => void;
  children: React.ReactNode;
}): React.JSX.Element {
  const active = summary !== undefined;

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
      <PopoverContent
        aria-label={`${label} filter`}
        className={cn(
          "gap-0 p-1",
          wide ? "max-h-(--available-height) w-80 overflow-y-auto" : "w-60",
        )}
      >
        {children}
        {active ? (
          <>
            <Separator className="my-1" />
            <Button variant="ghost" size="sm" className="w-full" onClick={onClear}>
              Clear {label.toLowerCase()}
            </Button>
          </>
        ) : null}
      </PopoverContent>
    </Popover>
  );
}
