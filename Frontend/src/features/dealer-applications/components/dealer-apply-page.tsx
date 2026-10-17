"use client";

import { CheckmarkCircle02Icon, LinkSquare02Icon } from "@hugeicons/core-free-icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { EmptyState } from "@/components/patterns/empty-state";
import { Notice } from "@/components/patterns/notice";
import { QueryView } from "@/components/patterns/query-view";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { OtpInput } from "@/components/ui/otp-input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  applicantViewQueryOptions,
  dealerApplicationKeys,
} from "@/features/dealer-applications/api/dealer-applications.queries";
import {
  checkApplicantCode,
  sendApplicantCode,
} from "@/features/dealer-applications/api/dealer-apply.api";
import type { ApplicantView } from "@/features/dealer-applications/api/dealer-apply.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import { DealerApplyForm } from "./dealer-apply-form";

const log = createLogger({
  file: "features/dealer-applications/components/dealer-apply-page.tsx",
  dataId: "CHNL-008",
});

/**
 * CHNL-008 · The page a prospective dealer opens from the link they were sent (FS-053),
 * on a phone, without an account: verify the mobile with a WhatsApp code, fill in the firm's
 * details, upload the documents, and submit. The session lives in this page only (two hours
 * on the backend): reopening the link asks for a code again.
 */
export function DealerApplyPage({ token }: { token: string }): React.JSX.Element {
  const [session, setSession] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const query = useQuery(applicantViewQueryOptions(token, session));

  if (query.isError && isApiError(query.error) && query.error.status === 404) {
    return (
      <EmptyState
        icon={LinkSquare02Icon}
        title="This link doesn't work any more"
        level={2}
        description="It may have expired, or a newer link was sent. Ask your Polysil contact for a new one."
        className="mt-6 rounded-xl border border-dashed border-border"
      />
    );
  }

  return (
    <QueryView query={query} pending={<ApplySkeleton />} isEmpty={() => false} empty={null}>
      {(view) => {
        if (view.status === "submitted") return <Submitted view={view} />;
        if (session === null || !view.verified) {
          return (
            <VerifyStep
              token={token}
              view={view}
              expired={expired}
              onVerified={(next) => {
                setExpired(false);
                setSession(next);
              }}
            />
          );
        }
        return (
          <DealerApplyForm
            token={token}
            session={session}
            view={view}
            onSessionLost={() => {
              setSession(null);
              setExpired(true);
            }}
          />
        );
      }}
    </QueryView>
  );
}

function Intro({ view }: { view: ApplicantView }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-1 pb-2">
      <h1 className="text-xl font-semibold text-foreground">Dealer application</h1>
      <p className="text-sm text-muted-foreground">{view.firmName}</p>
    </div>
  );
}

function Submitted({ view }: { view: ApplicantView }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-4">
      <Intro view={view} />
      <EmptyState
        icon={CheckmarkCircle02Icon}
        title="Submitted, we will be in touch"
        level={2}
        description="Polysil reviews your application. If something needs fixing, we'll send you the link again."
        className="rounded-xl border border-border"
      />
    </div>
  );
}

/** A WhatsApp code to the application's mobile, then the code typed in: a session. */
function VerifyStep({
  token,
  view,
  expired,
  onVerified,
}: {
  token: string;
  view: ApplicantView;
  expired: boolean;
  onVerified: (session: string) => void;
}): React.JSX.Element {
  const queryClient = useQueryClient();
  const [sent, setSent] = useState(false);
  const [code, setCode] = useState("");
  const [problem, setProblem] = useState<string | null>(null);

  const send = useAsyncAction({
    action: () => sendApplicantCode(token),
    logger: log,
    fn: "handleSendApplicantCode",
    dataId: "CHNL-008",
    onSuccess: () => {
      setSent(true);
      setProblem(null);
    },
    onError: (error) => {
      setProblem(
        isApiError(error) && error.code === "rate_limited"
          ? error.message
          : toUserFacingError(error).description,
      );
    },
  });

  const check = useAsyncAction({
    action: () => checkApplicantCode(token, code),
    logger: log,
    fn: "handleCheckApplicantCode",
    dataId: "CHNL-008",
    onSuccess: (session) => {
      void queryClient.invalidateQueries({
        queryKey: [...dealerApplicationKeys.all, "applicant", token],
      });
      onVerified(session);
    },
    onError: (error) => {
      setCode("");
      setProblem(
        isApiError(error) && error.code === "invalid_code"
          ? "That code didn't work. Check it, or ask for a new one."
          : toUserFacingError(error).description,
      );
    },
  });

  return (
    <div className="flex flex-col gap-4">
      <Intro view={view} />
      {expired ? (
        <Notice tone="warning">
          <p>Your session ended. Verify your mobile again to carry on; what you saved is kept.</p>
        </Notice>
      ) : null}
      {view.status === "returned" ? (
        <Notice tone="warning">
          <p>Polysil sent your application back. Verify your mobile to see what to fix.</p>
        </Notice>
      ) : null}
      <div className="flex flex-col gap-4 rounded-xl border border-border bg-card p-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-semibold text-foreground">Verify your mobile</h2>
          <p className="text-sm text-muted-foreground">
            We send a code on WhatsApp to {view.mobileMasked}, the number Polysil has for you.
          </p>
        </div>
        {sent ? (
          <form
            noValidate
            aria-label="Verify your mobile"
            className="flex flex-col gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (code.length < 6) {
                setProblem("Enter the 6-digit code.");
                return;
              }
              void check.run();
            }}
          >
            <Field data-invalid={problem === null ? undefined : true}>
              <FieldLabel id="apply-code-label">The code from WhatsApp</FieldLabel>
              <OtpInput
                aria-label="6-digit code"
                value={code}
                onValueChange={(next) => {
                  setCode(next);
                  setProblem(null);
                }}
                aria-invalid={problem === null ? undefined : true}
                aria-describedby={problem === null ? "apply-code-hint" : "apply-code-error"}
              />
              {problem === null ? (
                <FieldDescription id="apply-code-hint">
                  It works for a few minutes. Five wrong tries need a new code.
                </FieldDescription>
              ) : null}
              <FieldError id="apply-code-error">{problem ?? undefined}</FieldError>
            </Field>
            <div className="flex flex-wrap gap-2">
              <Button
                type="submit"
                state={check.state}
                loadingLabel="Checking…"
                successLabel="Verified"
                errorLabel="Not verified"
              >
                Verify
              </Button>
              <Button
                type="button"
                variant="ghost"
                state={send.state}
                loadingLabel="Sending…"
                onClick={() => {
                  void send.run();
                }}
              >
                Send a new code
              </Button>
            </div>
          </form>
        ) : (
          <div className="flex flex-col gap-2">
            {problem === null ? null : (
              <p role="alert" className="text-sm text-danger">
                {problem}
              </p>
            )}
            <Button
              className="self-start"
              state={send.state}
              loadingLabel="Sending…"
              successLabel="Sent"
              errorLabel="Not sent"
              onClick={() => {
                void send.run();
              }}
            >
              Send the code on WhatsApp
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

function ApplySkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading your application" className="flex flex-col gap-4">
      <Skeleton className="h-6 w-48" />
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}
