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
 */
export function PageTransition({ children }: { children: React.ReactNode }): React.JSX.Element {
  return (
    <ViewTransition enter={DIRECTIONAL} exit={DIRECTIONAL} default="none">
      {children}
    </ViewTransition>
  );
}
