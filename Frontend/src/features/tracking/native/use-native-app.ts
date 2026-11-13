"use client";

import { useSyncExternalStore } from "react";

import { isNativeApp } from "./tracking-bridge";

function subscribeNever(): () => void {
  return () => undefined;
}

/**
 * TRK-008 · True inside the Android app. False while the server renders and on its first client
 * pass, so the HTML always matches; the app's screens follow straight after.
 */
export function useIsNativeApp(): boolean {
  return useSyncExternalStore(subscribeNever, isNativeApp, () => false);
}
