"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Spinner } from "@/components/ui/spinner";
import { signInPath } from "@/lib/auth/redirects";
import {
  bootstrapSession,
  getAuthSnapshot,
  getServerAuthSnapshot,
  installAuthSession,
  retrySessionCheck,
  subscribeAuth,
} from "@/lib/auth/session-store";

/**
 * AUTH-006 · Renders signed-in pages only once this tab holds a session.
 *
 * proxy.ts has already sent visitors without a session marker to sign-in. Here the
 * tab exchanges its refresh cookie for an access token, then:
 *  - signed in      → the page
 *  - signed out     → cached data is dropped and the visitor goes to sign-in,
 *                     returning here afterwards unless they chose to sign out
 *  - backend down   → an error with a retry, instead of a false "signed out"
 */
export function AuthGate({ children }: { children: React.ReactNode }): React.JSX.Element {
  const auth = useSyncExternalStore(subscribeAuth, getAuthSnapshot, getServerAuthSnapshot);
  const router = useRouter();
  const queryClient = useQueryClient();

  useEffect(() => installAuthSession(), []);

  useEffect(() => {
    bootstrapSession();
  }, []);

  useEffect(() => {
    if (auth.status !== "signed-out") {
      return;
    }
    // Another user may sign in next on this device: nothing of this session may remain,
    // not even a toast about something they did.
    queryClient.clear();
    toast.dismiss();
    const next =
      auth.endReason === "signed-out"
        ? null
        : `${window.location.pathname}${window.location.search}`;
    router.replace(signInPath({ next, reason: auth.endReason }));
  }, [auth.status, auth.endReason, queryClient, router]);

  switch (auth.status) {
    case "signed-in":
      return <>{children}</>;
    case "unreachable":
      return (
        <main className="flex min-h-dvh items-center justify-center bg-background px-4">
          <ErrorState error={auth.error} onRetry={retrySessionCheck} />
        </main>
      );
    case "unknown":
    case "checking":
    case "signed-out":
      return <SessionSplash />;
  }
}

function SessionSplash(): React.JSX.Element {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-background px-4 text-sm text-muted-foreground">
      <Spinner label="Opening your workspace" className="size-5 text-primary" />
      <p aria-hidden="true">Opening your workspace…</p>
    </main>
  );
}
