"use client";

import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";
import type * as React from "react";

import { cn } from "@/lib/utils";

/**
 * The only way to render an icon. Icons come from the free Hugeicons pack:
 *
 *   import { Search01Icon } from "@hugeicons/core-free-icons";
 *   <Icon icon={Search01Icon} />
 *
 * Importing `@hugeicons/react` anywhere else is a lint error, so size and
 * stroke stay consistent across the app. Inside a Button the button decides
 * the icon size.
 */

export type IconGlyph = IconSvgElement;

const SIZE_CLASS = {
  xs: "size-3",
  sm: "size-3.5",
  md: "size-4",
  lg: "size-5",
  xl: "size-6",
} as const;

export interface IconProps extends Omit<
  React.ComponentProps<typeof HugeiconsIcon>,
  "icon" | "size" | "strokeWidth" | "color" | "altIcon" | "showAlt"
> {
  icon: IconGlyph;
  size?: keyof typeof SIZE_CLASS;
  /** 1.75 everywhere; 2 only for tiny glyphs that need weight (checkmarks). */
  strokeWidth?: 1.5 | 1.75 | 2;
  /** Accessible name. Omit for decorative icons — they are hidden from screen readers. */
  label?: string;
}

export function Icon({
  icon,
  size = "md",
  strokeWidth = 1.75,
  label,
  className,
  ...props
}: IconProps): React.JSX.Element {
  return (
    <HugeiconsIcon
      icon={icon}
      strokeWidth={strokeWidth}
      data-slot="icon"
      className={cn("shrink-0", SIZE_CLASS[size], className)}
      {...(label === undefined
        ? { "aria-hidden": true, focusable: false }
        : { "aria-label": label, role: "img" })}
      {...props}
    />
  );
}
