"use client";

import "./globals.css";

import { useEffect } from "react";
import type * as React from "react";

import { buttonVariants } from "@/components/ui/button-variants";
import { createLogger } from "@/lib/logger";

const log = createLogger({ file: "app/global-error.tsx", dataId: "APP-003" });

/** Last-resort boundary when the root layout itself fails. Renders its own <html>. */
export default function GlobalError({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}): React.JSX.Element {
  useEffect(() => {
    log.error("GlobalError", "root layout failed to render", {
      error,
      context: { digest: error.digest },
    });
  }, [error]);

  return (
    <html lang="en-IN">
      <body className="flex min-h-dvh items-center justify-center bg-background p-6 font-sans text-foreground">
        <div role="alert" className="flex max-w-sm flex-col items-center gap-3 text-center">
          <h1 className="text-lg font-semibold">Something went wrong</h1>
          <p className="text-sm text-muted-foreground">
            The app could not load. Try again, or reload the page.
          </p>
          {error.digest ? (
            <code className="rounded-sm bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
              {error.digest}
            </code>
          ) : null}
          <button
            type="button"
            onClick={() => {
              retry();
            }}
            className={buttonVariants()}
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
