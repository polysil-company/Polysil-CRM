"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { PencilEdit02Icon } from "@hugeicons/core-free-icons";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { useForm, useFormState } from "react-hook-form";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { OtpInput } from "@/components/ui/otp-input";
import { requestOtp, verifyOtp } from "@/features/auth/api/auth.api";
import {
  mobileNumberFormSchema,
  OTP_LENGTH,
  type MobileNumberFormInput,
  type MobileNumberFormValues,
  type OtpChallengeResponse,
} from "@/features/auth/api/auth.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useSecondsUntil } from "@/hooks/use-seconds-until";
import { readFieldErrors } from "@/lib/api/errors";
import type { SessionTokens } from "@/lib/auth/tokens";
import { describeCountdown, formatCountdown, formatIndianPhone } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import { SignInErrorAlert } from "./sign-in-error-alert";

const log = createLogger({
  file: "features/auth/components/mobile-sign-in.tsx",
  dataId: "AUTH-001",
});

interface Challenge {
  /** E.164 without the plus. */
  readonly mobile: string;
  /** Epoch ms when the code stops working. */
  readonly expiresAt: number;
  /** Epoch ms when a new code may be requested. */
  readonly resendAt: number;
}

function toChallenge(mobile: string, response: OtpChallengeResponse): Challenge {
  const now = Date.now();
  return {
    mobile,
    expiresAt: now + response.expiresInSeconds * 1000,
    resendAt: now + response.resendAfterSeconds * 1000,
  };
}

export interface MobileSignInProps {
  onSignedIn: (tokens: SessionTokens) => void;
}

/**
 * AUTH-001 · Channel partners sign in with a one-time code sent to their mobile.
 *
 * Step 1 asks for the number; step 2 takes the code. The backend answers step 1
 * the same way whether or not the number is registered, so step 2 never claims a
 * code was sent — only that one is on its way if the number is known.
 */
export function MobileSignIn({ onSignedIn }: MobileSignInProps): React.JSX.Element {
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [typedMobile, setTypedMobile] = useState("");
  const [changingNumber, setChangingNumber] = useState(false);

  if (challenge === null) {
    return (
      <MobileNumberStep
        defaultMobile={typedMobile}
        focusOnMount={changingNumber}
        onCodeRequested={(typed, next) => {
          setTypedMobile(typed);
          setChallenge(next);
        }}
      />
    );
  }

  return (
    <OtpCodeStep
      challenge={challenge}
      onChallengeRenewed={setChallenge}
      onChangeNumber={() => {
        setChangingNumber(true);
        setChallenge(null);
      }}
      onSignedIn={onSignedIn}
    />
  );
}

function MobileNumberStep({
  defaultMobile,
  focusOnMount,
  onCodeRequested,
}: {
  defaultMobile: string;
  focusOnMount: boolean;
  onCodeRequested: (typedMobile: string, challenge: Challenge) => void;
}): React.JSX.Element {
  const [formError, setFormError] = useState<unknown>(null);
  const form = useForm<MobileNumberFormInput, unknown, MobileNumberFormValues>({
    resolver: zodResolver(mobileNumberFormSchema),
    defaultValues: { mobile: defaultMobile },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  useEffect(() => {
    if (focusOnMount) {
      form.setFocus("mobile");
    }
  }, [focusOnMount, form]);

  const send = useAsyncAction({
    action: async ({ mobile }: MobileNumberFormValues) => ({
      mobile,
      response: await requestOtp(mobile),
    }),
    logger: log,
    fn: "handleRequestOtp",
    dataId: "AUTH-001",
    onSuccess: ({ mobile, response }) => {
      onCodeRequested(form.getValues("mobile"), toChallenge(mobile, response));
    },
    onError: (error) => {
      if (readFieldErrors(error)?.mobile !== undefined) {
        form.setError(
          "mobile",
          { type: "server", message: "Enter a 10-digit Indian mobile number." },
          { shouldFocus: true },
        );
        return;
      }
      setFormError(error);
    },
  });

  return (
    <form
      noValidate
      aria-label="Get a sign-in code"
      className="flex flex-col gap-4"
      onSubmit={(event) => {
        setFormError(null);
        void form.handleSubmit((values) => {
          void send.run(values);
        })(event);
      }}
    >
      <Field data-invalid={errors.mobile ? true : undefined}>
        <FieldLabel htmlFor="sign-in-mobile">Mobile number</FieldLabel>
        <InputGroup>
          <InputGroupAddon className="font-medium text-muted-foreground">+91</InputGroupAddon>
          <InputGroupInput
            id="sign-in-mobile"
            type="tel"
            inputMode="numeric"
            autoComplete="tel-national"
            placeholder="98765 43210"
            aria-invalid={errors.mobile ? true : undefined}
            aria-describedby={errors.mobile ? "sign-in-mobile-error" : "sign-in-mobile-help"}
            {...form.register("mobile")}
          />
        </InputGroup>
        {errors.mobile ? null : (
          <FieldDescription id="sign-in-mobile-help">
            Use the number registered with Polysil.
          </FieldDescription>
        )}
        <FieldError id="sign-in-mobile-error">{errors.mobile?.message}</FieldError>
      </Field>

      {formError === null ? null : <SignInErrorAlert error={formError} />}

      <Button
        type="submit"
        size="lg"
        className="mt-1 w-full"
        state={send.state}
        loadingLabel="Sending code…"
        successLabel="Code on its way"
        errorLabel="Not sent"
      >
        Send code
      </Button>
    </form>
  );
}

function OtpCodeStep({
  challenge,
  onChallengeRenewed,
  onChangeNumber,
  onSignedIn,
}: {
  challenge: Challenge;
  onChallengeRenewed: (challenge: Challenge) => void;
  onChangeNumber: () => void;
  onSignedIn: (tokens: SessionTokens) => void;
}): React.JSX.Element {
  const [code, setCode] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [resent, setResent] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const expiresIn = useSecondsUntil(challenge.expiresAt) ?? 0;
  const resendIn = useSecondsUntil(challenge.resendAt) ?? 0;
  const expired = expiresIn === 0;

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const verify = useAsyncAction({
    action: (value: string) => verifyOtp({ mobile: challenge.mobile, code: value }),
    logger: log,
    fn: "handleVerifyOtp",
    dataId: "AUTH-001",
    onSuccess: onSignedIn,
    onError: (caught) => {
      setError(caught);
      setCode("");
      inputRef.current?.focus();
    },
  });

  const resend = useAsyncAction({
    action: () => requestOtp(challenge.mobile),
    logger: log,
    fn: "handleResendOtp",
    dataId: "AUTH-001",
    onSuccess: (response) => {
      setError(null);
      setCode("");
      setResent(true);
      onChallengeRenewed(toChallenge(challenge.mobile, response));
      inputRef.current?.focus();
    },
    onError: setError,
  });

  const submitCode = (value: string): void => {
    if (value.length !== OTP_LENGTH || expired || verify.isBusy) {
      return;
    }
    setError(null);
    setResent(false);
    void verify.run(value);
  };

  return (
    <form
      noValidate
      aria-label="Enter your sign-in code"
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        submitCode(code);
      }}
    >
      <div className="flex flex-col items-start gap-1">
        <p className="text-sm text-muted-foreground">
          If{" "}
          <span className="font-medium whitespace-nowrap text-foreground tabular-nums">
            {formatIndianPhone(`+${challenge.mobile}`)}
          </span>{" "}
          is registered with Polysil, a {OTP_LENGTH}-digit code is on its way by SMS.
        </p>
        <Button
          type="button"
          variant="link"
          size="sm"
          disabled={verify.isBusy}
          onClick={onChangeNumber}
        >
          <Icon icon={PencilEdit02Icon} />
          Change number
        </Button>
      </div>

      <Field data-invalid={error ? true : undefined}>
        <FieldLabel htmlFor="sign-in-code">{OTP_LENGTH}-digit code</FieldLabel>
        <OtpInput
          ref={inputRef}
          id="sign-in-code"
          length={OTP_LENGTH}
          value={code}
          readOnly={verify.isBusy}
          disabled={expired}
          aria-invalid={error ? true : undefined}
          aria-describedby="sign-in-code-status"
          onValueChange={(value) => {
            setCode(value);
            if (error !== null) {
              setError(null);
            }
          }}
          onComplete={submitCode}
        />
        <p
          id="sign-in-code-status"
          className={cn("text-xs/normal", expired ? "text-warning" : "text-muted-foreground")}
        >
          {expired ? (
            "This code has expired. Send a new one to continue."
          ) : (
            <>
              Code expires in{" "}
              <span aria-hidden="true" className="tabular-nums">
                {formatCountdown(expiresIn)}
              </span>
              <span className="sr-only">{describeCountdown(expiresIn)}</span>
            </>
          )}
        </p>
      </Field>

      {error === null ? null : <SignInErrorAlert error={error} />}
      {resent && error === null ? (
        <p role="status" className="text-xs/normal text-success">
          A new code is on its way.
        </p>
      ) : null}

      <Button
        type="submit"
        size="lg"
        className="w-full"
        state={verify.state}
        disabled={code.length !== OTP_LENGTH || expired}
        loadingLabel="Verifying…"
        successLabel="Signed in"
        errorLabel="Not signed in"
      >
        Verify and sign in
      </Button>

      <div className="flex min-h-control-sm items-center justify-center text-center text-sm text-muted-foreground">
        {resendIn > 0 ? (
          <p>
            Didn&apos;t get it? Ask for a new code in{" "}
            <span aria-hidden="true" className="tabular-nums">
              {formatCountdown(resendIn)}
            </span>
            <span className="sr-only">{describeCountdown(resendIn)}</span>
          </p>
        ) : (
          <Button
            type="button"
            variant="link"
            size="sm"
            state={resend.state}
            loadingLabel="Sending…"
            successLabel="Sent"
            errorLabel="Not sent"
            onClick={() => {
              void resend.run();
            }}
          >
            Send a new code
          </Button>
        )}
      </div>
    </form>
  );
}
