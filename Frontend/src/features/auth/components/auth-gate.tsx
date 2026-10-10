"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useSyncExternalStore } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Spinner } from "@/components/ui/spinner";
import { sessionKeys } from "@/features/session/api/session.queries";
import type { Session } from "@/features/session/api/session.schemas";
import { useSession } from "@/features/session/hooks/use-session";
import { isApiError } from "@/lib/api/errors";
import { signInPath } from "@/lib/auth/redirects";
import {
  bootstrapSession,
  getAuthSnapshot,
  getServerAuthSnapshot,
  installAuthSession,
  retrySessionCheck,
  subscribeAuth,
} from "@/lib/auth/session-store";

import { ForcedPasswordChange } from "./forced-password-change";

/**
 * AUTH-006 · Renders signed-in pages only once this tab holds a session.
 *
 * proxy.ts has already sent visitors without a session marker to sign-in. Here the
 * tab exchanges its refresh cookie for an access token, then:
 *  - signed in      → the page
 *  - signed out     → cached data is dropped and the visitor goes to sign-in,
 *                     returning here afterwards unless they chose to sign out
 *  - backend down   → an error with a retry, instead of a false "signed out"
 *  - a temporary password in force → the forced password change (AUTH-007), nothing else
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
      return <PasswordChangeGate>{children}</PasswordChangeGate>;
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

function isPasswordChangeRequired(error: unknown): boolean {
  return isApiError(error) && error.status === 403 && error.code === "password_change_required";
}

/**
 * AUTH-007 · While a temporary password is in force the backend refuses every call but
 * `/auth/me` and `/auth/password`, so the app waits for `/auth/me` before rendering and shows
 * the password change instead when it says so. A `403 password_change_required` from any
 * query or mutation (an administrator reset the password mid-visit) switches to it too.
 */
function PasswordChangeGate({ children }: { children: React.ReactNode }): React.JSX.Element {
  const session = useSession();
  const queryClient = useQueryClient();

  useEffect(() => {
    const requireChange = (): void => {
      queryClient.setQueryData<Session>(sessionKeys.current(), (current) =>
        current === undefined ? current : { ...current, mustChangePassword: true },
      );
    };
    const stopQueries = queryClient.getQueryCache().subscribe((event) => {
      if (
        event.type === "updated" &&
        event.action.type === "error" &&
        isPasswordChangeRequired(event.action.error)
      ) {
        requireChange();
      }
    });
    const stopMutations = queryClient.getMutationCache().subscribe((event) => {
      if (
        event.type === "updated" &&
        event.action.type === "error" &&
        isPasswordChangeRequired(event.action.error)
      ) {
        requireChange();
      }
    });
    return () => {
      stopQueries();
      stopMutations();
    };
  }, [queryClient]);

  if (session.status === "pending") {
    return <SessionSplash />;
  }
  if (session.data?.mustChangePassword === true) {
    return <ForcedPasswordChange name={session.data.user.name} />;
  }
  return <>{children}</>;
}

function SessionSplash(): React.JSX.Element {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-background px-4 text-sm text-muted-foreground">
      <Spinner label="Opening your workspace" className="size-5 text-primary" />
      <p aria-hidden="true">Opening your workspace…</p>
    </main>
  );
}
