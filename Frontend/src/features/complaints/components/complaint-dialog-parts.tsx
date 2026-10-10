"use client";

import { useEffect, useRef } from "react";
import type * as React from "react";

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

/** The longest remark or reason the backend keeps. */
export const COMPLAINT_TEXT_MAX = 2000;

/** Closes a moment after success, and never after the dialog has gone. */
export function useCloseLater(onClose: () => void): () => void {
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    return () => {
      window.clearTimeout(timer.current);
    };
  }, []);
  return () => {
    timer.current = window.setTimeout(onClose, CLOSE_AFTER_SUCCESS_MS);
  };
}

/** A refusal the form can't pin on one field, said inside the dialog. */
export function Refusal({
  refusal,
}: {
  refusal: { title: string; message: string } | null;
}): React.JSX.Element | null {
  if (refusal === null) return null;
  return (
    <div
      role="alert"
      className="mt-4 flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
    >
      <p className="font-medium text-danger">{refusal.title}</p>
      <p className="text-foreground">{refusal.message}</p>
    </div>
  );
}
