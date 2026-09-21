import { clsx, type ClassValue } from "clsx";
import { extendTailwindMerge } from "tailwind-merge";

/**
 * tailwind-merge must know our custom scale, otherwise it treats e.g.
 * `text-2xs` as a colour and drops a real colour class next to it.
 * Keep these lists in sync with src/styles/tokens.css.
 */
const twMerge = extendTailwindMerge({
  extend: {
    theme: {
      text: ["2xs", "md"],
      radius: ["xs", "sm", "md", "lg", "xl", "2xl", "3xl"],
      shadow: ["xs", "sm", "md", "lg", "panel"],
      blur: ["2xs"],
      ease: ["drawer"],
      animate: ["shake", "indeterminate"],
      spacing: ["control-xs", "control-sm", "control-md", "control-lg", "sidebar", "header"],
    },
    classGroups: {
      duration: [{ duration: ["instant", "press", "fast", "base", "slow"] }],
      z: [
        "layer-sticky",
        "layer-header",
        "layer-overlay",
        "layer-modal",
        "layer-popover",
        "layer-toast",
        "layer-tooltip",
      ],
    },
  },
});

/** Merges class names, resolving Tailwind conflicts (the last one wins). */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
