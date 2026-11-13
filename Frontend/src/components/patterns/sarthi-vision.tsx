import Image from "next/image";
import type * as React from "react";

import chariot from "@/assets/brand/sarthi-vision.webp";
import { APP_VISION, APP_VISION_SPOKEN } from "@/lib/brand";
import { cn } from "@/lib/utils";

/** The file's own size. Given explicitly because in tests an image import is just a path. */
const CHARIOT_SIZE = { width: 384, height: 384 } as const;

/**
 * APP-013 · The chariot from the client's vision banner: Krishna as the charioteer, the
 * "Sarthi" the software is named for. Cut round from the banner they sent (13 Nov 2026).
 */
export function SarthiChariot({
  className,
  priority = false,
}: {
  className?: string;
  priority?: boolean;
}): React.JSX.Element {
  return (
    <Image
      src={chariot}
      {...CHARIOT_SIZE}
      alt="Krishna driving Arjuna's chariot: the Sarthi, or charioteer"
      priority={priority}
      className={cn("shrink-0 rounded-full object-cover", className)}
    />
  );
}

/**
 * APP-013 · "Vision · To Be The Sa₹thi of Farmer's Success". The rupee sign is kept for the eye
 * and swapped for plain words for a screen reader. `tone` picks the colours for the brand panel
 * (on primary) or a card.
 */
export function SarthiVision({
  tone = "card",
  className,
}: {
  tone?: "card" | "primary";
  className?: string;
}): React.JSX.Element {
  return (
    <figure className={cn("flex flex-col gap-1", className)}>
      <figcaption
        className={cn(
          "text-2xs font-semibold tracking-wider uppercase",
          tone === "primary" ? "text-primary-foreground/80" : "text-primary-text",
        )}
      >
        Our vision
      </figcaption>
      <blockquote
        className={cn(
          "font-semibold text-balance",
          tone === "primary" ? "text-2xl text-primary-foreground" : "text-sm text-foreground",
        )}
      >
        <span aria-hidden="true">{APP_VISION}</span>
        <span className="sr-only">{APP_VISION_SPOKEN}</span>
      </blockquote>
    </figure>
  );
}
