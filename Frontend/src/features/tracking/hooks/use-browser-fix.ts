"use client";

import { useCallback, useState } from "react";

import type { Fix } from "@/features/tracking/api/visits.schemas";

/** Where the browser's location request stands. */
export type FixState =
  | { readonly status: "idle" }
  | { readonly status: "locating" }
  | { readonly status: "ready"; readonly fix: Fix }
  | { readonly status: "denied" }
  | { readonly status: "unavailable" }
  | { readonly status: "failed" };

const OPTIONS: PositionOptions = { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 };

/**
 * TRK-003 · Ask the browser where the user is, for a check-in or check-out. Every outcome has
 * its own state, so the form can say what to do: allow location, move to open sky, or try again.
 */
export function useBrowserFix(): { readonly state: FixState; readonly locate: () => void } {
  const [state, setState] = useState<FixState>({ status: "idle" });

  const locate = useCallback(() => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      setState({ status: "unavailable" });
      return;
    }
    setState({ status: "locating" });
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setState({
          status: "ready",
          fix: {
            lat: position.coords.latitude,
            lng: position.coords.longitude,
            accuracyM: Number.isFinite(position.coords.accuracy)
              ? Math.round(position.coords.accuracy)
              : null,
            at: new Date(position.timestamp).toISOString(),
          },
        });
      },
      (error) => {
        setState({ status: error.code === error.PERMISSION_DENIED ? "denied" : "failed" });
      },
      OPTIONS,
    );
  }, []);

  return { state, locate };
}
