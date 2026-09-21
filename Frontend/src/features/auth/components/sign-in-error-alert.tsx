"use client";

import { Alert02Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { ErrorReference } from "@/components/patterns/error-state";
import { Icon } from "@/components/ui/icon";
import { describeSignInError } from "@/features/auth/lib/sign-in-errors";

/** What stopped the sign-in and what to do next, announced as it appears. */
export function SignInErrorAlert({ error }: { error: unknown }): React.JSX.Element {
  const view = describeSignInError(error);

  return (
    <div
      role="alert"
      className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm transition-[opacity,translate] duration-base ease-out starting:-translate-y-1 starting:opacity-0"
    >
      <p className="flex items-center gap-1.5 font-medium text-danger">
        <Icon icon={Alert02Icon} size="sm" />
        {view.title}
      </p>
      <p className="text-muted-foreground">{view.description}</p>
      {view.reference ? (
        <ErrorReference reference={view.reference} className="mt-1 self-start" />
      ) : null}
    </div>
  );
}
