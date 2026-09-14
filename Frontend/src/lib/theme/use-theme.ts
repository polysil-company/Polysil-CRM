"use client";

import { useSyncExternalStore } from "react";

import type { ResolvedTheme, ThemePreference } from "./theme";
import {
  getServerThemeSnapshot,
  getThemeSnapshot,
  setThemePreference,
  subscribeTheme,
} from "./theme-store";

export interface UseThemeResult {
  /** What the user chose. */
  readonly preference: ThemePreference;
  /** What is actually showing ("system" resolved against the OS). */
  readonly resolvedTheme: ResolvedTheme;
  readonly setPreference: (preference: ThemePreference) => void;
}

export function useTheme(): UseThemeResult {
  const snapshot = useSyncExternalStore(subscribeTheme, getThemeSnapshot, getServerThemeSnapshot);
  return {
    preference: snapshot.preference,
    resolvedTheme: snapshot.resolved,
    setPreference: setThemePreference,
  };
}
