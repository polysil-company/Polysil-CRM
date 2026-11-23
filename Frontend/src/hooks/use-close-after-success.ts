"use client";

import { useEffect, useRef } from "react";

/** How long a dialog shows its success before it closes. */
export const CLOSE_AFTER_SUCCESS_MS = 600;

/**
 * Returns `closeSoon()`: closes a dialog a moment after a save, so its button can show
 * "Saved" first. The timer is cleared when the dialog goes, and is never started once it has
 * gone: a save that finishes after the user closed the dialog (or after a test ended) has
 * nothing to close, and a timer then would fire into a page that no longer exists.
 */
export function useCloseAfterSuccess(
  onClose: () => void,
  ms: number = CLOSE_AFTER_SUCCESS_MS,
): () => void {
  const timer = useRef<number | undefined>(undefined);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      window.clearTimeout(timer.current);
    };
  }, []);

  return () => {
    if (!mounted.current) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(onClose, ms);
  };
}
