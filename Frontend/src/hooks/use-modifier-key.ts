"use client";

import { useSyncExternalStore } from "react";

export type ModifierKeyLabel = "⌘" | "Ctrl";

export function isApplePlatform(): boolean {
  return /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
}

function subscribeNever(): () => void {
  return () => undefined;
}

/** "⌘" on Apple devices, "Ctrl" elsewhere. Renders "Ctrl" on the server, then corrects after hydration. */
export function useModifierKeyLabel(): ModifierKeyLabel {
  return useSyncExternalStore(
    subscribeNever,
    () => (isApplePlatform() ? "⌘" : "Ctrl"),
    () => "Ctrl",
  );
}
