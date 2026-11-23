"use client";

import { Combobox as ComboboxPrimitive } from "@base-ui/react/combobox";
import { Cancel01Icon, Tick02Icon, UnfoldMoreIcon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { cn } from "@/lib/utils";

import { Icon } from "./icon";
import { InputGroup, InputGroupAddon, InputGroupInput } from "./input-group";
import { floatingSurfaceClasses } from "./popover";

/**
 * Based on shadcn/ui (base-nova) — restyled. A Select whose options are found by typing,
 * for lists too long to scroll: territories, people, products. Pass `filter={null}` and
 * the matching `items` when the search happens on the server.
 *
 *   <Combobox items={items} value={value} onValueChange={setValue} itemToStringLabel={…}>
 *     <ComboboxInput id="territory" placeholder="Search" />
 *     <ComboboxContent>
 *       <ComboboxStatus>{loading ? "Searching…" : null}</ComboboxStatus>
 *       <ComboboxEmpty>No matches.</ComboboxEmpty>
 *       <ComboboxList>{(item) => <ComboboxItem key={item.id} value={item}>…</ComboboxItem>}</ComboboxList>
 *     </ComboboxContent>
 *   </Combobox>
 */
export const Combobox = ComboboxPrimitive.Root;

/** Small square buttons inside the field; the pseudo-element grows the hit area on touch. */
const inFieldButtonClasses = cn(
  "relative flex size-control-xs items-center justify-center rounded-sm text-subtle-foreground transition-colors duration-fast",
  "after:absolute after:-inset-1.5 pointer-coarse:after:-inset-2.5",
  "hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-50",
);

export interface ComboboxInputProps extends Omit<ComboboxPrimitive.Input.Props, "className"> {
  className?: string;
  /** Adds a button that clears the chosen value. It shows only while there is one. */
  showClear?: boolean;
}

/** The text field, with a button that opens the list and an optional clear button. */
export function ComboboxInput({
  className,
  showClear = false,
  disabled = false,
  ...props
}: ComboboxInputProps): React.JSX.Element {
  return (
    <ComboboxPrimitive.InputGroup
      data-slot="combobox-input-group"
      render={<InputGroup />}
      className={cn("pr-1", className)}
    >
      <ComboboxPrimitive.Input
        data-slot="combobox-input"
        disabled={disabled}
        render={<InputGroupInput />}
        {...props}
      />
      <InputGroupAddon align="end" className="gap-0.5">
        {showClear ? (
          <ComboboxPrimitive.Clear
            data-slot="combobox-clear"
            aria-label="Clear"
            disabled={disabled}
            className={inFieldButtonClasses}
          >
            <Icon icon={Cancel01Icon} size="sm" />
          </ComboboxPrimitive.Clear>
        ) : null}
        <ComboboxPrimitive.Trigger
          data-slot="combobox-trigger"
          aria-label="Show options"
          disabled={disabled}
          className={inFieldButtonClasses}
        >
          <Icon icon={UnfoldMoreIcon} />
        </ComboboxPrimitive.Trigger>
      </InputGroupAddon>
    </ComboboxPrimitive.InputGroup>
  );
}

export interface ComboboxContentProps
  extends
    Omit<ComboboxPrimitive.Popup.Props, "className">,
    Pick<ComboboxPrimitive.Positioner.Props, "align" | "alignOffset" | "side" | "sideOffset"> {
  className?: string;
}

/** The floating panel, as wide as the field. Grows from the field, like every popup. */
export function ComboboxContent({
  className,
  side = "bottom",
  sideOffset = 6,
  align = "start",
  alignOffset = 0,
  ...props
}: ComboboxContentProps): React.JSX.Element {
  return (
    <ComboboxPrimitive.Portal>
      <ComboboxPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        className="layer-popover"
      >
        <ComboboxPrimitive.Popup
          data-slot="combobox-content"
          className={cn(
            floatingSurfaceClasses,
            "flex max-h-(--available-height) w-(--anchor-width) max-w-(--available-width) flex-col overflow-hidden",
            className,
          )}
          {...props}
        />
      </ComboboxPrimitive.Positioner>
    </ComboboxPrimitive.Portal>
  );
}

export function ComboboxList({
  className,
  ...props
}: Omit<ComboboxPrimitive.List.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <ComboboxPrimitive.List
      data-slot="combobox-list"
      className={cn(
        "max-h-72 scroll-py-1 scrollbar-thin overflow-y-auto overscroll-contain p-1 data-empty:p-0",
        className,
      )}
      {...props}
    />
  );
}

export function ComboboxItem({
  className,
  children,
  ...props
}: Omit<ComboboxPrimitive.Item.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <ComboboxPrimitive.Item
      data-slot="combobox-item"
      className={cn(
        "relative flex w-full cursor-default items-center gap-2 rounded-md py-1.5 pr-8 pl-2 text-sm text-foreground outline-none select-none pointer-coarse:min-h-control-lg",
        "data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-accent",
        className,
      )}
      {...props}
    >
      {children}
      <ComboboxPrimitive.ItemIndicator className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
        <Icon icon={Tick02Icon} strokeWidth={2} />
      </ComboboxPrimitive.ItemIndicator>
    </ComboboxPrimitive.Item>
  );
}

/**
 * Loading, error and hint messages, announced politely. Keep it mounted and change its
 * children: screen readers only announce a live region that was already on the page.
 */
export function ComboboxStatus({
  className,
  ...props
}: Omit<ComboboxPrimitive.Status.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <ComboboxPrimitive.Status
      data-slot="combobox-status"
      className={cn(
        "flex items-center gap-2 text-sm text-muted-foreground not-empty:px-3 not-empty:py-2",
        className,
      )}
      {...props}
    />
  );
}

/** Shown only when the list has no items. Keep it mounted, like the status. */
export function ComboboxEmpty({
  className,
  ...props
}: Omit<ComboboxPrimitive.Empty.Props, "className"> & { className?: string }): React.JSX.Element {
  return (
    <ComboboxPrimitive.Empty
      data-slot="combobox-empty"
      className={cn("text-sm text-muted-foreground not-empty:px-3 not-empty:py-2", className)}
      {...props}
    />
  );
}
