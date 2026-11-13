"use client";

import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { Alert02Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import type { AsyncActionState } from "@/hooks/use-async-action";
import { cn } from "@/lib/utils";

import { buttonVariants, type ButtonVariantProps } from "./button-variants";
import { Icon } from "./icon";
import { ProgressRing } from "./spinner";

/**
 * Based on shadcn/ui (base-nova, Base UI) — restyled to Polysil tokens.
 *
 * Plain button: <Button>Save</Button>
 * Async button: pass `state` (drive it with `useAsyncAction`):
 *   <Button state={save.state} loadingLabel="Saving…" successLabel="Saved">Save</Button>
 * All labels share one grid cell, so the width never jumps between states.
 * Style a link as a button with `buttonVariants` from ./button-variants.
 */

export type ButtonState = AsyncActionState;

export interface ButtonProps extends Omit<ButtonPrimitive.Props, "className">, ButtonVariantProps {
  className?: string;
  /** Enables async feedback. Omit for a plain button. */
  state?: ButtonState;
  /** 0–100 while loading: shows a determinate ring instead of a spinner. */
  progress?: number | undefined;
  loadingLabel?: string;
  successLabel?: string;
  errorLabel?: string;
}

export function Button({
  className,
  variant,
  size,
  state,
  progress,
  loadingLabel,
  successLabel,
  errorLabel,
  disabled,
  children,
  ...props
}: ButtonProps): React.JSX.Element {
  if (state === undefined) {
    return (
      <ButtonPrimitive
        data-slot="button"
        disabled={disabled}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      >
        {children}
      </ButtonPrimitive>
    );
  }

  const busy = state === "loading";
  const announcement =
    state === "loading"
      ? (loadingLabel ?? "Working")
      : state === "success"
        ? (successLabel ?? "Done")
        : state === "error"
          ? (errorLabel ?? "Failed")
          : "";

  return (
    <>
      <ButtonPrimitive
        data-slot="button"
        data-state={state}
        aria-busy={busy || undefined}
        disabled={disabled === true || busy}
        focusableWhenDisabled={busy}
        className={cn(
          buttonVariants({ variant, size }),
          "data-[state=loading]:cursor-progress data-[state=loading]:data-disabled:opacity-100",
          "data-[state=error]:animate-shake motion-reduce:data-[state=error]:animate-none",
          className,
        )}
        {...props}
      >
        <span className="grid place-items-center *:col-start-1 *:row-start-1">
          <StateLayer active={state === "idle"}>{children}</StateLayer>
          <StateLayer active={busy}>
            <ProgressRing value={progress} />
            {loadingLabel}
          </StateLayer>
          <StateLayer active={state === "success"}>
            <CheckMark drawn={state === "success"} />
            {successLabel}
          </StateLayer>
          <StateLayer active={state === "error"}>
            <Icon icon={Alert02Icon} />
            {errorLabel}
          </StateLayer>
        </span>
      </ButtonPrimitive>
      <span className="sr-only" role="status" aria-live="polite">
        {announcement}
      </span>
    </>
  );
}

function StateLayer({
  active,
  children,
}: {
  active: boolean;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <span
      data-active={active}
      aria-hidden={!active}
      className="inline-flex items-center justify-center gap-1.5 transition-[opacity,filter,scale] duration-base ease-out data-[active=false]:pointer-events-none data-[active=false]:scale-95 data-[active=false]:opacity-0 data-[active=false]:blur-2xs"
    >
      {children}
    </span>
  );
}

function CheckMark({ drawn }: { drawn: boolean }): React.JSX.Element {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" className="size-4">
      <path
        d="M3.5 8.5l3 3 6-7"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        pathLength={1}
        data-drawn={drawn}
        className="draw-path data-[drawn=true]:draw-path-drawn"
      />
    </svg>
  );
}
