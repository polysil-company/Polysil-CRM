"use client";

import { useEffect, useRef, useState } from "react";

export interface CopyToClipboard {
  readonly copied: boolean;
  /** Resolves false when the clipboard is unavailable (e.g. insecure context). */
  copy: (text: string) => Promise<boolean>;
}

export function useCopyToClipboard(resetMs = 1500): CopyToClipboard {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    return () => {
      clearTimeout(timer.current);
    };
  }, []);

  const copy = async (text: string): Promise<boolean> => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return false;
    }
    setCopied(true);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setCopied(false);
    }, resetMs);
    return true;
  };

  return { copied, copy };
}
