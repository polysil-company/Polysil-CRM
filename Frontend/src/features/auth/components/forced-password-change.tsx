"use client";

import { LockPasswordIcon } from "@hugeicons/core-free-icons";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { Icon } from "@/components/ui/icon";
import { useSignOut } from "@/features/auth/hooks/use-sign-out";

import { AuthFrame } from "./auth-frame";
import { ChangePasswordForm } from "./change-password-form";

/**
 * AUTH-007 · Shown instead of the app while a temporary password is in force: the backend
 * refuses every other call until it is changed, so there is nothing else to show. After the
 * change every session is signed out, and the person signs in with their new password.
 */
export function ForcedPasswordChange({ name }: { name: string }): React.JSX.Element {
  const { signOut, isSigningOut } = useSignOut();

  return (
    <AuthFrame>
      <div className="flex w-full max-w-sm flex-col gap-6">
        <header className="flex flex-col gap-2">
          <span className="flex size-10 items-center justify-center rounded-full bg-primary-soft text-primary">
            <Icon icon={LockPasswordIcon} />
          </span>
          <h1 className="text-xl font-semibold text-foreground">Choose your own password</h1>
          <p className="text-sm text-muted-foreground">
            Welcome, {name}. Your administrator gave you a temporary password. Choose your own to
            start using Polysil CRM; then sign in again with it.
          </p>
        </header>

        <ChangePasswordForm temporary />

        <p className="text-center text-sm text-muted-foreground">
          Not you?{" "}
          <Button
            variant="link"
            className="h-auto p-0"
            disabled={isSigningOut}
            onClick={() => {
              void signOut();
            }}
          >
            {isSigningOut ? "Signing out…" : "Sign out"}
          </Button>
        </p>
      </div>
    </AuthFrame>
  );
}
