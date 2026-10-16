import type * as React from "react";

import { EMPTY_VALUE } from "@/lib/format";
import { cn } from "@/lib/utils";

const WIDTH = 96;
const HEIGHT = 28;
const PADDING = 2;

export type SparklineTone = "primary" | "success" | "danger" | "muted";

const toneClasses: Readonly<Record<SparklineTone, string>> = {
  primary: "text-primary",
  success: "text-success",
  danger: "text-danger",
  muted: "text-subtle-foreground",
};

export interface SparklinePoint {
  readonly x: number;
  readonly y: number;
}

/** Maps values onto the sparkline viewBox. A flat series draws a centred line. */
export function buildSparklinePoints(values: readonly number[]): SparklinePoint[] {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min;
  const step = values.length > 1 ? (WIDTH - PADDING * 2) / (values.length - 1) : 0;

  return values.map((value, index) => ({
    x: PADDING + index * step,
    y: range === 0 ? HEIGHT / 2 : PADDING + (1 - (value - min) / range) * (HEIGHT - PADDING * 2),
  }));
}

/** Screen-reader summary: "Leads per week: rising, from 3 to 9". */
export function describeTrend(values: readonly number[], subject: string): string {
  const first = values[0];
  const last = values.at(-1);
  if (first === undefined || last === undefined) {
    return `${subject}: no data`;
  }
  const direction = last > first ? "rising" : last < first ? "falling" : "flat";
  return `${subject}: ${direction}, from ${first} to ${last}`;
}

export interface SparklineProps {
  values: readonly number[];
  /** Accessible summary — use describeTrend(). */
  label: string;
  tone?: SparklineTone;
  area?: boolean;
  className?: string;
}

/** Tiny inline trend chart. Decorative detail around a number that is shown as text elsewhere. */
export function Sparkline({
  values,
  label,
  tone = "primary",
  area = true,
  className,
}: SparklineProps): React.JSX.Element {
  const series = values.filter((value) => Number.isFinite(value));
  const points = series.length >= 2 ? buildSparklinePoints(series) : [];
  const first = points[0];
  const last = points.at(-1);

  if (!first || !last) {
    return <span className="text-xs text-subtle-foreground">{EMPTY_VALUE}</span>;
  }

  const line = points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ");

  return (
    <svg
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label={label}
      className={cn("h-7 w-24 shrink-0 overflow-visible", toneClasses[tone], className)}
    >
      {area ? (
        <path
          d={`M${first.x},${HEIGHT} L${line.replaceAll(" ", " L")} L${last.x},${HEIGHT} Z`}
          className="fill-current opacity-10"
        />
      ) : null}
      <polyline
        points={line}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={last.x} cy={last.y} r={2} className="fill-current" />
    </svg>
  );
}
