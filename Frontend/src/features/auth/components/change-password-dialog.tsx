"use client";

import type * as React from "react";

import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { ChangePasswordForm } from "./change-password-form";

/**
 * AUTH-007 · Change your password from the account menu (staff; partners sign in by code).
 * Render it inside a `Dialog`; the menu owns the open state.
 */
export function ChangePasswordDialogContent(): React.JSX.Element {
  return (
    <DialogContent size="sm">
      <DialogHeader>
        <DialogTitle>Change password</DialogTitle>
        <DialogDescription>
          You&apos;ll be signed out on every device, then sign in with the new password.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <ChangePasswordForm
          secondaryAction={
            <DialogClose render={<Button type="button" variant="outline" />}>Cancel</DialogClose>
          }
        />
      </DialogBody>
    </DialogContent>
  );
}
