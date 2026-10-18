"use client";

import { StarIcon } from "@hugeicons/core-free-icons";
import { useId } from "react";
import type * as React from "react";

import { Icon } from "@/components/ui/icon";
import { cn } from "@/lib/utils";

const SCORES = [1, 2, 3, 4, 5] as const;

/** "1 star", "4 stars". */
function starsText(score: number): string {
  return score === 1 ? "1 star" : `${String(score)} stars`;
}

/**
 * A score out of five as stars, read out as "4 out of 5 stars". The stars are decoration: the
 * accessible name always carries the number.
 */
export function StarRating({
  score,
  size = "sm",
  className,
}: {
  /** 1 to 5; anything else is clamped. */
  score: number;
  size?: "xs" | "sm" | "md";
  className?: string;
}): React.JSX.Element {
  const shown = Math.min(5, Math.max(0, Math.round(score)));
  return (
    <span
      role="img"
      aria-label={`${String(shown)} out of 5 stars`}
      className={cn("inline-flex items-center gap-0.5", className)}
    >
      {SCORES.map((star) => (
        <Icon
          key={star}
          icon={StarIcon}
          size={size}
          className={star <= shown ? "fill-current text-warning" : "text-muted-foreground/50"}
        />
      ))}
    </span>
  );
}

/**
 * Choose 1 to 5 stars. Native radio buttons under a fieldset, so arrow keys move between them
 * and a screen reader names each one ("4 stars, Good"). Each star is a 44px touch target.
 */
export function StarRatingInput({
  value,
  onValueChange,
  legend,
  describe,
  invalid,
  disabled,
}: {
  value: number | null;
  onValueChange: (score: number) => void;
  /** What is being rated; read before the stars. */
  legend: string;
  /** Words for each score ("Good"), shown under the stars and read with each one. */
  describe?: (score: number) => string;
  invalid?: boolean;
  disabled?: boolean;
}): React.JSX.Element {
  const name = useId();
  const word = value === null || describe === undefined ? null : describe(value);
  return (
    <fieldset disabled={disabled} aria-invalid={invalid} className="flex flex-col gap-1">
      <legend className="mb-1 text-sm font-medium text-foreground">{legend}</legend>
      <div className="-ml-2.5 flex items-center">
        {SCORES.map((score) => {
          const on = value !== null && score <= value;
          return (
            <label
              key={score}
              className={cn(
                "relative flex size-11 press-scale cursor-pointer items-center justify-center rounded-md",
                "has-focus-visible:outline-2 has-focus-visible:-outline-offset-2 has-focus-visible:outline-ring",
                "has-disabled:cursor-not-allowed has-disabled:opacity-50",
              )}
            >
              <input
                type="radio"
                name={name}
                value={score}
                checked={value === score}
                onChange={() => {
                  onValueChange(score);
                }}
                aria-label={
                  describe === undefined
                    ? starsText(score)
                    : `${starsText(score)}, ${describe(score)}`
                }
                className="peer sr-only"
              />
              <Icon
                icon={StarIcon}
                size="xl"
                className={cn(
                  "transition-colors duration-fast",
                  on
                    ? "fill-current text-warning"
                    : invalid === true
                      ? "text-danger"
                      : "text-muted-foreground",
                )}
              />
            </label>
          );
        })}
      </div>
      <p aria-hidden="true" className="min-h-5 text-sm text-muted-foreground">
        {word === null ? "Choose 1 to 5 stars." : `${starsText(value ?? 0)}: ${word}`}
      </p>
    </fieldset>
  );
}
