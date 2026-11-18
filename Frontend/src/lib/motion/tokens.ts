/**
 * Motion tokens for JavaScript animations (Motion, formerly Framer Motion).
 *
 * Mirrors the easing and duration tokens in src/styles/tokens.css — CSS is the
 * source of truth. `tokens.test.ts` parses the CSS and fails if these drift.
 *
 * Prefer CSS transitions (interruptible, off the main thread). Use Motion only
 * for layout animations, gestures, springs and presence (enter/exit of
 * conditionally rendered elements).
 */

export type CubicBezier = [number, number, number, number];

/** Entering/exiting: out. Moving on screen: inOut. Sheets and drawers: drawer. Never ease-in. */
export const EASE: Readonly<Record<"out" | "inOut" | "drawer", CubicBezier>> = {
  out: [0.23, 1, 0.32, 1],
  inOut: [0.77, 0, 0.175, 1],
  drawer: [0.32, 0.72, 0, 1],
};

/** Seconds — Motion's unit. CSS equivalents: --duration-* in milliseconds. */
export const DURATION = {
  instant: 0,
  press: 0.12,
  fast: 0.15,
  base: 0.2,
  slow: 0.3,
} as const;

/** Springs for gestures and interruptible movement. Keep bounce subtle. */
export const SPRING = {
  snappy: { type: "spring", duration: 0.35, bounce: 0.1 },
  gentle: { type: "spring", duration: 0.5, bounce: 0.15 },
} as const;
