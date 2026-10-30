"use client";

import type * as React from "react";

/** The longest remark or reason the backend keeps. */
export const COMPLAINT_TEXT_MAX = 2000;

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
