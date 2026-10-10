"use client";

import {
  CheckmarkCircle02Icon,
  Clock01Icon,
  Mail01Icon,
  SmartPhone01Icon,
} from "@hugeicons/core-free-icons";
import { useQueryClient } from "@tanstack/react-query";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import type * as React from "react";
import { toast } from "sonner";

import { Icon } from "@/components/ui/icon";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { HOME_PATH, type SessionEndReason } from "@/lib/auth/redirects";
import { acceptSessionTokens } from "@/lib/auth/session-store";
import type { SessionTokens } from "@/lib/auth/tokens";
import { MOCK_OTP_CODE, MOCK_STAFF_PASSWORD } from "@/lib/dev/mock-settings";
import { clientEnv } from "@/lib/env/client";

import { MobileSignIn } from "./mobile-sign-in";
import { StaffSignInForm } from "./staff-sign-in-form";

export const SIGN_IN_METHODS = ["mobile", "staff"] as const;

export type SignInMethod = (typeof SIGN_IN_METHODS)[number];

const METHOD_COPY: Readonly<Record<SignInMethod, string>> = {
  mobile: "Channel partners get a one-time code on their registered mobile.",
  staff: "Polysil staff sign in with their work email and password.",
};

export interface SignInScreenProps {
  /** A safe same-site path to open after signing in. */
  next: Route | null;
  /** Why the visitor is here, when a session just ended. */
  reason: SessionEndReason | null;
}

/**
 * The sign-in page. The method lives in the URL (?method=staff), so a staff
 * bookmark opens straight to the email form.
 */
export function SignInScreen({ next, reason }: SignInScreenProps): React.JSX.Element {
  const router = useRouter();
  const queryClient = useQueryClient();
  // After a password change only staff sign in again, so the email form opens first.
  const [method, setMethod] = useQueryState(
    "method",
    parseAsStringLiteral(SIGN_IN_METHODS).withDefault(
      reason === "password-changed" || reason === "password-reset" ? "staff" : "mobile",
    ),
  );

  const finishSignIn = (tokens: SessionTokens): void => {
    // Nothing cached or shown before sign-in belongs to this user.
    queryClient.clear();
    toast.dismiss();
    acceptSessionTokens(tokens);
    router.replace(next ?? HOME_PATH);
  };

  return (
    <div className="flex w-full max-w-sm flex-col gap-6">
      <header className="flex flex-col gap-1.5">
        <h1 className="text-xl font-semibold text-foreground">Sign in</h1>
        <p className="text-sm text-muted-foreground">{METHOD_COPY[method]}</p>
      </header>

      {reason === null ? null : <SessionEndNotice reason={reason} />}

      <ToggleGroup
        aria-label="How do you sign in?"
        value={[method]}
        onValueChange={(values) => {
          const chosen = SIGN_IN_METHODS.find((candidate) => candidate === values[0]);
          // Pressing the active option again keeps it selected.
          if (chosen !== undefined) {
            void setMethod(chosen);
          }
        }}
        className="w-full"
      >
        <ToggleGroupItem value="mobile" className="h-control-md flex-1 pointer-coarse:h-control-lg">
          <Icon icon={SmartPhone01Icon} />
          Mobile number
        </ToggleGroupItem>
        <ToggleGroupItem value="staff" className="h-control-md flex-1 pointer-coarse:h-control-lg">
          <Icon icon={Mail01Icon} />
          Staff email
        </ToggleGroupItem>
      </ToggleGroup>

      <div
        key={method}
        className="transition-[opacity,translate] duration-base ease-out starting:translate-y-1 starting:opacity-0"
      >
        {method === "mobile" ? (
          <MobileSignIn onSignedIn={finishSignIn} />
        ) : (
          <StaffSignInForm onSignedIn={finishSignIn} />
        )}
      </div>

      {clientEnv.apiMocking === "enabled" ? <MockCredentialsHint method={method} /> : null}
    </div>
  );
}

const SESSION_END_COPY: Readonly<
  Record<SessionEndReason, { title: string; body: string; done: boolean }>
> = {
  "signed-out": {
    title: "You've signed out",
    body: "Sign in again whenever you're ready.",
    done: true,
  },
  "session-ended": {
    title: "Your session has ended",
    body: "Sign in again to pick up where you left off.",
    done: false,
  },
  "password-changed": {
    title: "Password changed",
    body: "You were signed out everywhere. Sign in with your new password.",
    done: true,
  },
  "password-reset": {
    title: "Your administrator set a new password",
    body: "It was set while you were changing yours. Sign in with the password they gave you.",
    done: false,
  },
};

function SessionEndNotice({ reason }: { reason: SessionEndReason }): React.JSX.Element {
  const copy = SESSION_END_COPY[reason];

  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-lg border border-border bg-card p-3 text-sm shadow-xs"
    >
      <Icon
        icon={copy.done ? CheckmarkCircle02Icon : Clock01Icon}
        className={copy.done ? "mt-0.5 text-success" : "mt-0.5 text-info"}
      />
      <div className="flex flex-col gap-0.5">
        <p className="font-medium text-foreground">{copy.title}</p>
        <p className="text-muted-foreground">{copy.body}</p>
      </div>
    </div>
  );
}

function MockCredentialsHint({ method }: { method: SignInMethod }): React.JSX.Element {
  return (
    <p className="rounded-md border border-dashed border-border-strong bg-muted px-3 py-2 text-xs/normal text-muted-foreground">
      <span className="font-medium text-foreground">Mock backend · </span>
      {method === "mobile" ? (
        <>
          Any Indian mobile number, then code{" "}
          <code className="font-mono text-foreground">{MOCK_OTP_CODE}</code>.
        </>
      ) : (
        <>
          Any email, with password{" "}
          <code className="font-mono text-foreground">{MOCK_STAFF_PASSWORD}</code>.
        </>
      )}
    </p>
  );
}
