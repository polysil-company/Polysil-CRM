"use client";

import type * as React from "react";

export interface InlineScriptProps {
  /** Trusted, constant JavaScript. Never pass user input. */
  html: string;
}

/**
 * A script that runs while the browser parses the server HTML, before first paint
 * (e.g. applying the saved theme).
 *
 * React warns whenever it renders a `<script>` in the browser, because such scripts
 * never run there — which happens when the root layout is re-rendered on the client,
 * for instance after recovering from an error. On the server this renders a real
 * script; in the browser it renders an inert `text/plain` one, and
 * `suppressHydrationWarning` accepts the difference.
 * Pattern from the Next.js guide "Preventing flash before hydration".
 */
export function InlineScript({ html }: InlineScriptProps): React.JSX.Element {
  return (
    <script
      type={typeof window === "undefined" ? "text/javascript" : "text/plain"}
      suppressHydrationWarning
      // eslint-disable-next-line react/no-danger -- Callers pass constant, trusted code (see the prop's contract).
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
