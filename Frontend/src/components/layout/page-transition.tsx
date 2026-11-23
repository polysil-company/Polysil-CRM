import { ViewTransition } from "react";
import type * as React from "react";

const DIRECTIONAL = {
  "nav-forward": "nav-forward",
  "nav-back": "nav-back",
  default: "none",
} as const;

/**
 * APP-003 · Wrap each PAGE's content (never a layout — layouts persist, so
 * their enter/exit never fire). Links and router calls pass
 * `transitionTypes={["nav-forward"]}` or `["nav-back"]`; anything else (back
 * button, redirects) swaps instantly. Animations: src/styles/tokens.css §7.
 *
 * Only the page being left animates: it slides and fades out over the new one. The new page
 * is never captured, because Chrome doesn't hit-test a captured element until the transition
 * ends, so the first click on a page that had just arrived went to nothing (walk F-13).
 */
export function PageTransition({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <ViewTransition enter="none" exit={DIRECTIONAL} default="none">
      {children}
    </ViewTransition>
  );
}
