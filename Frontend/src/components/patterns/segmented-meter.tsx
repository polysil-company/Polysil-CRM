import type * as React from "react";

import { formatPercent } from "@/lib/format";
import { cn } from "@/lib/utils";

export type MeterTone = "primary" | "success" | "warning" | "danger";

const fillClasses: Readonly<Record<MeterTone, string>> = {
  primary: "bg-primary",
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
};

/** Low → danger, middle → warning, high → success. */
export function meterToneFor(ratio: number): MeterTone {
  if (ratio >= 0.67) return "success";
  if (ratio >= 0.34) return "warning";
  return "danger";
}

export interface SegmentedMeterProps {
  value: number;
  max?: number;
  segments?: number;
  /** Accessible name, e.g. "Win probability". */
  label: string;
  /** Fixed tone; omit to derive it from the value. */
  tone?: MeterTone;
  showValue?: boolean;
  className?: string;
}

/**
 * A row of short segments — reads like drip emitters along a line. For
 * probability, completion and scores. Exposed to assistive tech as a meter.
 */
export function SegmentedMeter({
  value,
  max = 100,
  segments = 5,
  label,
  tone,
  showValue = true,
  className,
}: SegmentedMeterProps): React.JSX.Element {
  const safeMax = max > 0 ? max : 100;
  const clamped = Math.min(safeMax, Math.max(0, Number.isFinite(value) ? value : 0));
  const ratio = clamped / safeMax;
  const filled = Math.round(ratio * segments);
  const resolvedTone = tone ?? meterToneFor(ratio);
  const percent = formatPercent(ratio * 100);

  return (
    <div
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={clamped}
      aria-valuetext={percent}
      className={cn("flex items-center gap-2", className)}
    >
      <span aria-hidden="true" className="flex items-center gap-0.5">
        {Array.from({ length: segments }, (_, index) => (
          <span
            key={index}
            className={cn(
              "h-3 w-1.5 rounded-full transition-colors duration-base",
              index < filled ? fillClasses[resolvedTone] : "bg-accent-strong",
            )}
          />
        ))}
      </span>
      {showValue ? (
        <span className="w-9 text-xs font-medium text-muted-foreground tabular-nums">
          {percent}
        </span>
      ) : null}
    </div>
  );
}
