import type * as React from "react";

import { cn } from "@/lib/utils";

const RADIUS = 6;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;
/** Visible arc of the indeterminate spinner, as a fraction of the circle. */
const INDETERMINATE_ARC = 0.3;

export interface ProgressRingProps extends Omit<React.ComponentProps<"svg">, "children"> {
  /** 0–100 renders a determinate ring. Omit for an indeterminate spinner. */
  value?: number | undefined;
}

/**
 * The single circular loader used across the app — in buttons, inline
 * loading and progress. Decorative: pair it with visible or sr-only text.
 */
export function ProgressRing({ value, className, ...props }: ProgressRingProps): React.JSX.Element {
  const determinate = value !== undefined;
  const fraction = determinate ? Math.min(100, Math.max(0, value)) / 100 : INDETERMINATE_ARC;

  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      data-slot="progress-ring"
      className={cn("size-4 shrink-0", !determinate && "animate-spin", className)}
      {...props}
    >
      <circle cx="8" cy="8" r={RADIUS} stroke="currentColor" strokeOpacity={0.2} strokeWidth={2} />
      <circle
        cx="8"
        cy="8"
        r={RADIUS}
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeDasharray={CIRCUMFERENCE}
        strokeDashoffset={CIRCUMFERENCE * (1 - fraction)}
        className="origin-center -rotate-90 transition-[stroke-dashoffset] duration-base ease-out"
      />
    </svg>
  );
}

export interface SpinnerProps extends ProgressRingProps {
  /** When set, announces loading to screen readers. */
  label?: string;
}

export function Spinner({ label, ...props }: SpinnerProps): React.JSX.Element {
  if (label === undefined) {
    return <ProgressRing {...props} />;
  }
  return (
    <span role="status" className="inline-flex items-center">
      <ProgressRing {...props} />
      <span className="sr-only">{label}</span>
    </span>
  );
}
