"use client";

import { motion, useReducedMotion } from "motion/react";
import type * as React from "react";

import { cn } from "@/lib/utils";

const VIEW_WIDTH = 480;
const VIEW_HEIGHT = 640;
const ROW_COUNT = 9;
const ROW_GAP = 68;
const FIRST_ROW_Y = 44;
const EMITTER_GAP = 48;

/** [row, emitter, delay in seconds] — fixed, so the pattern is identical on every render. */
const DRIPS: readonly (readonly [number, number, number])[] = [
  [0, 3, 0],
  [1, 7, 1.3],
  [2, 2, 2.4],
  [3, 6, 0.6],
  [4, 1, 1.9],
  [5, 8, 3.1],
  [6, 4, 0.9],
  [7, 6, 2.7],
  [8, 2, 1.6],
];

function emitterX(row: number, emitter: number): number {
  // Alternate rows are offset half a gap, like staggered laterals in a field.
  return 16 + emitter * EMITTER_GAP + (row % 2) * (EMITTER_GAP / 2);
}

function rowY(row: number): number {
  return FIRST_ROW_Y + row * ROW_GAP;
}

/**
 * Decorative drip-irrigation laterals for the sign-in brand panel: rows of pipe,
 * emitters along each row, and the occasional drop. Colour comes from
 * `currentColor`. Seen once per sign-in, so a slow ambient loop is acceptable;
 * with reduced motion the drops are not drawn at all.
 */
export function DripField({ className }: { className?: string }): React.JSX.Element {
  const reduceMotion = useReducedMotion();
  const rows = Array.from({ length: ROW_COUNT }, (_, row) => row);
  const emitters = Array.from({ length: 10 }, (_, emitter) => emitter);

  return (
    <svg
      viewBox={`0 0 ${VIEW_WIDTH} ${VIEW_HEIGHT}`}
      preserveAspectRatio="xMidYMid slice"
      fill="none"
      aria-hidden="true"
      className={cn("size-full", className)}
    >
      {rows.map((row) => (
        <g key={row}>
          <line
            x1={0}
            x2={VIEW_WIDTH}
            y1={rowY(row)}
            y2={rowY(row)}
            stroke="currentColor"
            strokeOpacity={0.18}
            strokeWidth={2}
          />
          {emitters.map((emitter) => (
            <circle
              key={emitter}
              cx={emitterX(row, emitter)}
              cy={rowY(row)}
              r={3}
              fill="currentColor"
              fillOpacity={0.38}
            />
          ))}
        </g>
      ))}
      {reduceMotion === true
        ? null
        : DRIPS.map(([row, emitter, delay]) => (
            <motion.ellipse
              key={`${row}-${emitter}`}
              cx={emitterX(row, emitter)}
              cy={rowY(row) + 9}
              rx={2.5}
              ry={3.5}
              fill="currentColor"
              initial={{ opacity: 0, transform: "translateY(-4px)" }}
              animate={{
                opacity: [0, 0.85, 0],
                transform: ["translateY(-4px)", "translateY(4px)", "translateY(18px)"],
              }}
              transition={{
                duration: 2.4,
                times: [0, 0.35, 1],
                ease: "easeInOut",
                delay,
                repeat: Infinity,
                repeatDelay: 2.2,
              }}
            />
          ))}
    </svg>
  );
}
