"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import type * as React from "react";
import { useForm, useFormState } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { PasswordInput } from "@/components/ui/password-input";
import { changeOwnPassword } from "@/features/auth/api/auth.api";
import {
  changePasswordFormSchema,
  PASSWORD_MIN_LENGTH,
  type ChangePasswordFormInput,
  type ChangePasswordFormValues,
} from "@/features/auth/api/auth.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { endSession } from "@/lib/auth/session-store";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import { SignInErrorAlert } from "./sign-in-error-alert";

const log = createLogger({
  file: "features/auth/components/change-password-form.tsx",
  dataId: "AUTH-007",
});

/** The backend's word for a wrong current password is "wrong"; anything else is shown as sent. */
function currentPasswordMessage(reason: string): string {
  return reason === "wrong" ? "That isn't your current password." : reason;
}

function newPasswordMessage(reason: string): string {
  return /^at (least|most) \d+ characters$/.test(reason)
    ? `${reason.charAt(0).toUpperCase()}${reason.slice(1)}.`
    : reason;
}

export interface ChangePasswordFormProps {
  /** Labels the current password as the temporary one the administrator gave. */
  temporary?: boolean;
  /** Shown beside the submit button, e.g. Cancel in a dialog. */
  secondaryAction?: React.ReactNode;
  className?: string;
}

/**
 * AUTH-007 · Change your own password: the current one, then the new one twice. The backend
 * signs every session out once it accepts the change, this one included, so success ends the
 * session here and the sign-in page says to use the new password. A reset by an administrator
 * in the meantime (409 `password_changed_meanwhile`) ends it too, saying to use theirs.
 */
export function ChangePasswordForm({
  temporary = false,
  secondaryAction,
  className,
}: ChangePasswordFormProps): React.JSX.Element {
  const idempotency = useIdempotencyKey();
  const [formError, setFormError] = useState<unknown>(null);
  const form = useForm<ChangePasswordFormInput, unknown, ChangePasswordFormValues>({
    resolver: zodResolver(changePasswordFormSchema),
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  const submit = useAsyncAction({
    action: (values: ChangePasswordFormValues) => {
      const body = { current_password: values.currentPassword, new_password: values.newPassword };
      return changeOwnPassword({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleChangePassword",
    dataId: "AUTH-007",
    onSuccess: () => {
      idempotency.reset();
      endSession("password-changed");
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "password_changed_meanwhile") {
        endSession("password-reset");
        return;
      }
      const fields = readFieldErrors(error);
      const current = fields?.current_password;
      const next = fields?.new_password;
      if (current !== undefined || next !== undefined) {
        if (current !== undefined) {
          form.setError("currentPassword", {
            type: "server",
            message: currentPasswordMessage(current),
          });
          form.resetField("currentPassword", { keepError: true });
          form.setFocus("currentPassword");
        }
        if (next !== undefined) {
          form.setError("newPassword", { type: "server", message: newPasswordMessage(next) });
        }
        return;
      }
      setFormError(error);
    },
  });

  return (
    <form
      noValidate
      aria-label="Change your password"
      className={cn("flex flex-col gap-4", className)}
      onSubmit={(event) => {
        setFormError(null);
        void form.handleSubmit((values) => {
          void submit.run(values);
        })(event);
      }}
    >
      <Field data-invalid={errors.currentPassword ? true : undefined}>
        <FieldLabel htmlFor="current-password">
          {temporary ? "Temporary password" : "Current password"}
        </FieldLabel>
        <PasswordInput
          id="current-password"
          autoComplete="current-password"
          aria-invalid={errors.currentPassword ? true : undefined}
          aria-describedby={errors.currentPassword ? "current-password-error" : undefined}
          {...form.register("currentPassword")}
        />
        <FieldError id="current-password-error">{errors.currentPassword?.message}</FieldError>
      </Field>

      <Field data-invalid={errors.newPassword ? true : undefined}>
        <FieldLabel htmlFor="new-password">New password</FieldLabel>
        <PasswordInput
          id="new-password"
          autoComplete="new-password"
          aria-invalid={errors.newPassword ? true : undefined}
          aria-describedby={errors.newPassword ? "new-password-error" : "new-password-help"}
          {...form.register("newPassword")}
        />
        {errors.newPassword ? null : (
          <FieldDescription id="new-password-help">
            At least {PASSWORD_MIN_LENGTH} characters. A short sentence is easy to remember.
          </FieldDescription>
        )}
        <FieldError id="new-password-error">{errors.newPassword?.message}</FieldError>
      </Field>

      <Field data-invalid={errors.confirmPassword ? true : undefined}>
        <FieldLabel htmlFor="confirm-password">New password, again</FieldLabel>
        <PasswordInput
          id="confirm-password"
          autoComplete="new-password"
          aria-invalid={errors.confirmPassword ? true : undefined}
          aria-describedby={errors.confirmPassword ? "confirm-password-error" : undefined}
          {...form.register("confirmPassword")}
        />
        <FieldError id="confirm-password-error">{errors.confirmPassword?.message}</FieldError>
      </Field>

      {formError === null ? null : <SignInErrorAlert error={formError} />}

      <div className="mt-1 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {secondaryAction}
        <Button
          type="submit"
          {...(secondaryAction === undefined ? { className: "w-full", size: "lg" as const } : {})}
          state={submit.state}
          loadingLabel="Changing…"
          successLabel="Changed"
          errorLabel="Not changed"
        >
          Change password
        </Button>
      </div>
    </form>
  );
}
