"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import type * as React from "react";
import { useForm, useFormState } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { signInWithPassword } from "@/features/auth/api/auth.api";
import {
  staffSignInFormSchema,
  type StaffSignInFormInput,
  type StaffSignInRequest,
} from "@/features/auth/api/auth.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import type { SessionTokens } from "@/lib/auth/tokens";
import { createLogger } from "@/lib/logger";

import { SignInErrorAlert } from "./sign-in-error-alert";

const log = createLogger({
  file: "features/auth/components/staff-sign-in-form.tsx",
  dataId: "AUTH-003",
});

export interface StaffSignInFormProps {
  onSignedIn: (tokens: SessionTokens) => void;
}

/**
 * AUTH-003 · Polysil staff sign in with their work email and password.
 * Validation runs on blur, then on change. A rejected password clears the
 * password field and returns focus to it; the email stays.
 */
export function StaffSignInForm({ onSignedIn }: StaffSignInFormProps): React.JSX.Element {
  const [formError, setFormError] = useState<unknown>(null);
  const form = useForm<StaffSignInFormInput, unknown, StaffSignInRequest>({
    resolver: zodResolver(staffSignInFormSchema),
    defaultValues: { email: "", password: "" },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  const submit = useAsyncAction({
    action: (credentials: StaffSignInRequest) => signInWithPassword(credentials),
    logger: log,
    fn: "handleStaffSignIn",
    dataId: "AUTH-003",
    onSuccess: onSignedIn,
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields?.email !== undefined || fields?.password !== undefined) {
        if (fields.email !== undefined) {
          form.setError("email", { type: "server", message: "Enter a valid email address." });
        }
        if (fields.password !== undefined) {
          form.setError("password", { type: "server", message: "Enter your password." });
        }
        return;
      }
      setFormError(error);
      if (isApiError(error) && error.code === "invalid_credentials") {
        form.resetField("password");
        form.setFocus("password");
      }
    },
  });

  return (
    <form
      noValidate
      aria-label="Sign in with your work email"
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        setFormError(null);
        void form.handleSubmit((credentials) => {
          void submit.run(credentials);
        })(event);
      }}
    >
      <Field data-invalid={errors.email ? true : undefined}>
        <FieldLabel htmlFor="sign-in-email">Work email</FieldLabel>
        <Input
          id="sign-in-email"
          type="email"
          inputMode="email"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={errors.email ? "sign-in-email-error" : undefined}
          {...form.register("email")}
        />
        <FieldError id="sign-in-email-error">{errors.email?.message}</FieldError>
      </Field>

      <Field data-invalid={errors.password ? true : undefined}>
        <FieldLabel htmlFor="sign-in-password">Password</FieldLabel>
        <PasswordInput
          id="sign-in-password"
          autoComplete="current-password"
          aria-invalid={errors.password ? true : undefined}
          aria-describedby={errors.password ? "sign-in-password-error" : "sign-in-password-help"}
          {...form.register("password")}
        />
        {errors.password ? null : (
          <FieldDescription id="sign-in-password-help">
            Forgot it? Ask your administrator to reset it.
          </FieldDescription>
        )}
        <FieldError id="sign-in-password-error">{errors.password?.message}</FieldError>
      </Field>

      {formError === null ? null : <SignInErrorAlert error={formError} />}

      <Button
        type="submit"
        size="lg"
        className="mt-1 w-full"
        state={submit.state}
        loadingLabel="Signing in…"
        successLabel="Signed in"
        errorLabel="Not signed in"
      >
        Sign in
      </Button>
    </form>
  );
}
