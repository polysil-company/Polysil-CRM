"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { Fix } from "@/features/tracking/api/visits.schemas";
import { checkTrackingPermissions, isNativeApp } from "@/features/tracking/native/tracking-bridge";

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
 * TRK-003 · Whether location is already allowed, so it can be taken without asking: Android's own
 * permission inside the app, the browser's for this site elsewhere. False when it can't be told.
 */
export async function locationAlreadyAllowed(): Promise<boolean> {
  try {
    if (isNativeApp()) return (await checkTrackingPermissions()).location === "granted";
    if (typeof navigator === "undefined" || !("permissions" in navigator)) return false;
    const status = await navigator.permissions.query({ name: "geolocation" });
    return status.state === "granted";
  } catch {
    return false;
  }
}

/**
 * TRK-003 · Ask the browser where the user is, for a check-in or check-out. Every outcome has
 * its own state, so the form can say what to do: allow location, move to open sky, or try again.
 *
 * With `autoWhenAllowed`, a fresh fix is taken as soon as the form opens if location is already
 * allowed (client ask, 30 Oct). The first time, the person still taps Locate me, so Android's
 * permission question comes from their own tap and never pops up by surprise.
 */
export function useBrowserFix({ autoWhenAllowed = false }: { autoWhenAllowed?: boolean } = {}): {
  readonly state: FixState;
  readonly locate: () => void;
} {
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

  // Once per form: reading where the device is, not fetching data for the screen.
  const tried = useRef(false);
  useEffect(() => {
    if (!autoWhenAllowed || tried.current) return;
    tried.current = true;
    let cancelled = false;
    void locationAlreadyAllowed().then((allowed) => {
      if (allowed && !cancelled) locate();
    });
    return () => {
      cancelled = true;
    };
  }, [autoWhenAllowed, locate]);

  return { state, locate };
}

/** TRK-008 · One fresh fix, for going on and off duty; refused with the reason when there's none. */
export function getOneFix(): Promise<Fix> {
  return new Promise((resolve, reject) => {
    if (typeof navigator === "undefined" || !("geolocation" in navigator)) {
      reject(new Error("unavailable"));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
          accuracyM: Number.isFinite(position.coords.accuracy)
            ? Math.round(position.coords.accuracy)
            : null,
          at: new Date(position.timestamp).toISOString(),
        });
      },
      (error) => {
        reject(new Error(error.code === error.PERMISSION_DENIED ? "denied" : "failed"));
      },
      OPTIONS,
    );
  });
}
