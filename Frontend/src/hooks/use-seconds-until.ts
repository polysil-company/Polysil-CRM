"use client";

import { useSyncExternalStore } from "react";

const TICK_MS = 1000;

const listeners = new Set<() => void>();
let now = Date.now();
let timer: ReturnType<typeof setInterval> | undefined;

function tick(): void {
  now = Date.now();
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === undefined) {
    now = Date.now();
    timer = setInterval(tick, TICK_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== undefined) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

function subscribeNever(): () => void {
  return () => undefined;
}

function getSnapshot(): number {
  return now;
}

/**
 * Whole seconds until `deadline` (epoch ms), updated every second and never below 0.
 * Null when there is no deadline, in which case nothing ticks.
 *
 * Every countdown on screen shares one timer, so they change together.
 */
export function useSecondsUntil(deadline: number | null): number | null {
  const current = useSyncExternalStore(
    deadline === null ? subscribeNever : subscribe,
    getSnapshot,
    getSnapshot,
  );
  if (deadline === null) {
    return null;
  }
  return Math.max(0, Math.ceil((deadline - current) / 1000));
}
