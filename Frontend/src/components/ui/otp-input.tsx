"use client";

import { useState } from "react";
import type * as React from "react";

import { cn } from "@/lib/utils";

export interface OtpInputProps extends Omit<
  React.ComponentProps<"input">,
  "value" | "defaultValue" | "onChange" | "type" | "maxLength" | "className" | "children"
> {
  /** Digits only, at most `length` of them. */
  value: string;
  onValueChange: (value: string) => void;
  /** Called when the last slot is filled — typed, pasted or autofilled. */
  onComplete?: (value: string) => void;
  length?: number;
  className?: string;
}

function moveCaretToEnd(input: HTMLInputElement): void {
  const end = input.value.length;
  if (input.selectionStart !== end || input.selectionEnd !== end) {
    input.setSelectionRange(end, end);
  }
}

/**
 * One-time code entry: a row of digit slots over ONE real input.
 *
 * A single input (rather than one per digit) keeps the platform behaviour people
 * rely on: SMS code autofill on iOS and Android (`autocomplete="one-time-code"`),
 * pasting the whole code, backspace, and a single label for screen readers.
 * The slots are decoration drawn from its value. Non-digits are dropped, so
 * pasting "482 913" works.
 *
 *   <OtpInput aria-label="6-digit code" value={code} onValueChange={setCode} onComplete={verify} />
 */
export function OtpInput({
  value,
  onValueChange,
  onComplete,
  length = 6,
  disabled,
  className,
  onFocus,
  onBlur,
  onSelect,
  ...props
}: OtpInputProps): React.JSX.Element {
  const [focused, setFocused] = useState(false);
  const digits = value.replace(/\D/g, "").slice(0, length);
  const activeIndex = Math.min(digits.length, length - 1);
  const invalid = props["aria-invalid"] === true || props["aria-invalid"] === "true";

  return (
    <div
      data-slot="otp-input"
      data-disabled={disabled ? true : undefined}
      className={cn("relative w-fit", disabled && "opacity-50", className)}
    >
      <input
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        pattern={`\\d{${length}}`}
        spellCheck={false}
        disabled={disabled}
        value={digits}
        onChange={(event) => {
          const next = event.target.value.replace(/\D/g, "").slice(0, length);
          onValueChange(next);
          if (next.length === length && digits.length < length) {
            onComplete?.(next);
          }
        }}
        onFocus={(event) => {
          setFocused(true);
          moveCaretToEnd(event.currentTarget);
          onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          onBlur?.(event);
        }}
        onSelect={(event) => {
          // Typing always fills the next slot, so the caret stays at the end.
          moveCaretToEnd(event.currentTarget);
          onSelect?.(event);
        }}
        className="absolute inset-0 size-full bg-transparent font-mono text-transparent caret-transparent outline-none selection:bg-transparent focus-visible:outline-none disabled:cursor-not-allowed"
        {...props}
      />
      <div aria-hidden="true" className="pointer-events-none flex gap-2">
        {Array.from({ length }, (_, index) => {
          const digit = digits[index];
          const active = focused && index === activeIndex;
          return (
            <div
              key={index}
              data-active={active}
              data-filled={digit !== undefined}
              className={cn(
                "flex size-control-lg items-center justify-center rounded-md border border-input bg-card font-mono text-xl text-foreground shadow-xs transition-[border-color,outline-color] duration-fast ease-out",
                "data-[filled=true]:border-border-strong",
                "data-[active=true]:border-ring data-[active=true]:outline-2 data-[active=true]:outline-offset-0 data-[active=true]:outline-ring/30 data-[active=true]:outline-solid",
                invalid && "border-danger data-[filled=true]:border-danger",
              )}
            >
              {digit === undefined ? (
                active ? (
                  <span className="h-5 w-px animate-caret-blink bg-foreground motion-reduce:animate-none" />
                ) : null
              ) : (
                <span
                  key={digit}
                  className="transition-[opacity,scale] duration-fast ease-out starting:scale-95 starting:opacity-0"
                >
                  {digit}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
