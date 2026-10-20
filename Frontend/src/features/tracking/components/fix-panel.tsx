"use client";

import { Location01Icon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { Spinner } from "@/components/ui/spinner";
import { FIX_WARN_METRES } from "@/features/tracking/api/visits.schemas";
import type { FixState } from "@/features/tracking/hooks/use-browser-fix";
import { formatNumber } from "@/lib/format";

/**
 * TRK-003, TRK-004 · Where the browser says the user is, and how sure: a warning above 100 m,
 * and what to do when the location is refused or can't be had.
 */
export function FixPanel({
  state,
  onLocate,
}: {
  state: FixState;
  onLocate: () => void;
}): React.JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex flex-col gap-2 rounded-lg border border-border bg-muted/40 p-3"
    >
      <div className="flex items-start gap-2">
        <Icon icon={Location01Icon} className="mt-0.5 text-muted-foreground" />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5 text-sm">
          {state.status === "locating" ? (
            <span className="flex items-center gap-2 text-foreground">
              <Spinner />
              Finding where you are…
            </span>
          ) : state.status === "ready" ? (
            <>
              <span className="text-foreground tabular-nums">
                Located{" "}
                {state.fix.accuracyM === null
                  ? ""
                  : `to within ${formatNumber(state.fix.accuracyM)} m`}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {state.fix.lat.toFixed(5)}, {state.fix.lng.toFixed(5)}
              </span>
              {state.fix.accuracyM !== null && state.fix.accuracyM > FIX_WARN_METRES ? (
                <span className="text-xs font-medium text-warning">
                  That&apos;s rough. Step outside or wait a moment, then locate again.
                </span>
              ) : null}
            </>
          ) : state.status === "denied" ? (
            <span className="text-danger">
              Location is blocked for this site. Allow it in the browser&apos;s site settings, then
              try again.
            </span>
          ) : state.status === "unavailable" ? (
            <span className="text-danger">This browser can&apos;t share your location.</span>
          ) : state.status === "failed" ? (
            <span className="text-danger">Your location couldn&apos;t be found. Try again.</span>
          ) : (
            <span className="text-muted-foreground">Your location is taken when you check in.</span>
          )}
        </div>
      </div>
      {state.status === "locating" || state.status === "unavailable" ? null : (
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={onLocate}>
          {state.status === "idle" ? "Locate me" : "Locate again"}
        </Button>
      )}
    </div>
  );
}
