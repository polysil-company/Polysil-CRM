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
  className?: string;
}

/**
 * A thin horizontal share bar. Decorative — always show the number it
 * represents as text next to it.
 */
export function ProportionBar({
  value,
  max,
  tone = "primary",
  className,
}: ProportionBarProps): React.JSX.Element {
  const percent = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 100 8"
      preserveAspectRatio="none"
      className={cn("h-2 w-full overflow-hidden rounded-full", className)}
    >
      <rect width="100" height="8" className="fill-accent-strong" />
      <rect width={percent} height="8" className={fillClasses[tone]} />
    </svg>
  );
}
