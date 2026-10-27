import Image from "next/image";
import type * as React from "react";

import logo from "@/assets/brand/polysil-logo.png";
import mark from "@/assets/brand/polysil-mark.png";
import { cn } from "@/lib/utils";

/**
 * APP-010 · Polysil's leaf on a white tile, as on the app icon: where a square fits beside a
 * name (sidebar, portal). Cut from the logo the backend prints on quotation PDFs
 * (`backend/worker/templates/assets/polysil-logo.png`) by `mobile/scripts/make-brand-assets.mjs`.
 * Decorative: the name beside it says who it is.
 */
export function BrandMark({ className }: { className?: string }): React.JSX.Element {
  return (
    <Image
      src={mark}
      alt=""
      aria-hidden="true"
      className={cn("shrink-0 rounded-md object-contain", className)}
    />
  );
}

/**
 * APP-010 · The full logo, leaf and "POLYSIL · Shaping water", on white so it reads in dark mode
 * too (its white wave line is transparent): where there is room for it, as on sign-in. Set the
 * height; the width follows.
 */
export function BrandLogo({
  className,
  priority = false,
}: {
  className?: string;
  /** Above the fold on the first page a visitor sees, such as sign-in. */
  priority?: boolean;
}): React.JSX.Element {
  return (
    <Image
      src={logo}
      alt="Polysil Irrigation"
      priority={priority}
      className={cn("h-10 w-auto shrink-0 rounded-lg object-contain", className)}
    />
  );
}
