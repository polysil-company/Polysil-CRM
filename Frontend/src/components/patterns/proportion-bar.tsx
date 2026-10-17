import type * as React from "react";

import { cn } from "@/lib/utils";

export type ProportionTone = "primary" | "success" | "warning" | "danger";

const fillClasses: Readonly<Record<ProportionTone, string>> = {
  primary: "fill-primary",
  success: "fill-success",
  warning: "fill-warning",
  danger: "fill-danger",
};

export interface ProportionBarProps {
  value: number;
  max: number;
  tone?: ProportionTone;
  /** A mark on the same scale as `value`, such as a target: a thin line across the bar. */
  marker?: number;
  className?: string;
}

/** Percent of the track, kept between 0 and 100. */
function share(value: number, max: number): number {
  return max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
}

/**
 * A thin horizontal share bar. Decorative — always show the number it
 * represents (and the marker's) as text next to it.
 */
export function ProportionBar({
  value,
  max,
  tone = "primary",
  marker,
  className,
}: ProportionBarProps): React.JSX.Element {
  const percent = share(value, max);
  // Kept off the very ends, where the rounded track would clip half the line.
  const markerAt = marker === undefined ? null : Math.min(99, Math.max(1, share(marker, max)));

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 8"
      preserveAspectRatio="none"
      className={cn("h-2 w-full overflow-hidden rounded-full", className)}
    >
      <rect width="100" height="8" className="fill-accent-strong" />
      <rect width={percent} height="8" className={fillClasses[tone]} />
      {markerAt === null ? null : (
        <g data-slot="marker">
          {/* A ring of the card's colour keeps the line apart from the fill it crosses. */}
          <line
            x1={markerAt}
            x2={markerAt}
            y1="0"
            y2="8"
            strokeWidth={4}
            vectorEffect="non-scaling-stroke"
            className="stroke-card"
          />
          <line
            x1={markerAt}
            x2={markerAt}
            y1="0"
            y2="8"
            strokeWidth={2}
            vectorEffect="non-scaling-stroke"
            className="stroke-foreground"
          />
        </g>
      )}
    </svg>
  );
}
