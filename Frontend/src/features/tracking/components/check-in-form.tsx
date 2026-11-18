"use client";

import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";
import { z } from "zod";

import { Notice } from "@/components/patterns/notice";
import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { DealerPicker, type DealerChoice } from "@/features/complaints/components/dealer-picker";
import type { Visit } from "@/features/tracking/api/tracking.schemas";
import { useAcceptConsent, useCheckIn } from "@/features/tracking/api/visits.mutations";
import type { CheckInRequest, TrackingConfig } from "@/features/tracking/api/visits.schemas";
import { useBrowserFix } from "@/features/tracking/hooks/use-browser-fix";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { createLogger } from "@/lib/logger";

import { FixPanel } from "./fix-panel";
import { VisitLeadPicker, type LeadChoice } from "./visit-lead-picker";

const log = createLogger({
  file: "features/tracking/components/check-in-form.tsx",
  dataId: "TRK-003",
});

const TARGETS = ["lead", "dealer", "place"] as const;
type Target = (typeof TARGETS)[number];

const TARGET_LABELS: Readonly<Record<Target, string>> = {
  lead: "A lead",
  dealer: "A dealer",
  place: "Another place",
};

const openVisitSchema = z.object({ fields: z.object({ visit_id: z.string().min(1) }) });

/** The open visit a 409 `visit_open` names, or null. */
export function openVisitIdOf(error: unknown): string | null {
  if (!isApiError(error) || error.code !== "visit_open") return null;
  const parsed = openVisitSchema.safeParse(error.details);
  return parsed.success ? parsed.data.fields.visit_id : null;
}

/**
 * TRK-003 · Check in at a lead, a dealer or a named place, with the browser's location. The
 * consent is asked first when this version isn't accepted yet. An open visit is named, with a
 * way to open it. Every attempt gets a new visit id and key, as the contract asks after a 4xx.
 */
export function CheckInForm({
  config,
  onDone,
  onOpenVisit,
}: {
  config: TrackingConfig;
  onDone: (visit: Visit) => void;
  onOpenVisit: (visitId: string) => void;
}): React.JSX.Element {
  const [step, setStep] = useState<"form" | "consent">(
    config.consent.accepted ? "form" : "consent",
  );
  const [target, setTarget] = useState<Target>("lead");
  const [lead, setLead] = useState<LeadChoice | null>(null);
  const [dealer, setDealer] = useState<DealerChoice | null>(null);
  const [place, setPlace] = useState("");
  const [visitId, setVisitId] = useState(createRequestId);
  const [problem, setProblem] = useState<string | null>(null);
  const [openVisit, setOpenVisit] = useState<string | null>(null);
  const { state: fix, locate } = useBrowserFix({ autoWhenAllowed: true });
  const checkIn = useCheckIn();
  const consent = useAcceptConsent();
  const keys = useIdempotencyKey();

  const chosen =
    target === "lead" ? lead !== null : target === "dealer" ? dealer !== null : place.trim() !== "";

  const bodyOf = (): CheckInRequest | null => {
    if (fix.status !== "ready") return null;
    return {
      id: visitId,
      lead_id: target === "lead" ? (lead?.id ?? null) : null,
      partner_id: target === "dealer" ? (dealer?.id ?? null) : null,
      place_name: target === "place" ? place.trim() : null,
      at: fix.fix.at,
      sent_at: new Date().toISOString(),
      lat: fix.fix.lat,
      lng: fix.fix.lng,
      accuracy_m: fix.fix.accuracyM,
    };
  };

  /** After a refusal: a fresh visit id and key for the next try. */
  const freshAttempt = (): void => {
    keys.reset();
    setVisitId(createRequestId());
  };

  const save = useAsyncAction({
    action: () => {
      const body = bodyOf();
      if (body === null) throw new Error("No location yet");
      return checkIn.mutateAsync({ body, idempotencyKey: keys.keyFor(body) });
    },
    logger: log,
    fn: "handleCheckIn",
    dataId: "TRK-003",
    onSuccess: (visit) => {
      toast.success("Checked in", { description: visit.label });
      onDone(visit);
    },
    onError: (error) => {
      freshAttempt();
      if (isApiError(error) && error.code === "consent_required") {
        setStep("consent");
        return;
      }
      const open = openVisitIdOf(error);
      if (open !== null) {
        setOpenVisit(open);
        return;
      }
      if (isApiError(error) && error.status === 404) {
        setProblem("That lead or dealer isn't one you can visit. Pick another.");
        return;
      }
      const fields = readFieldErrors(error);
      const first = fields === null ? undefined : Object.values(fields)[0];
      if (first !== undefined) {
        setProblem(first);
        return;
      }
      toast.error("Not checked in", { description: toUserFacingError(error).description });
    },
  });

  const accept = useAsyncAction({
    action: () =>
      consent.mutateAsync({
        version: config.consent.requiredVersion,
        idempotencyKey: createRequestId(),
      }),
    logger: log,
    fn: "handleAcceptConsent",
    dataId: "TRK-003",
    onSuccess: () => {
      setStep("form");
    },
    onError: (error) => {
      toast.error("Consent not saved", { description: toUserFacingError(error).description });
    },
  });

  if (step === "consent") {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <DialogHeader>
          <DialogTitle>Location tracking</DialogTitle>
          <DialogDescription>Read this once before your first check-in.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <p className="text-sm whitespace-pre-line text-foreground">{config.consent.text}</p>
        </DialogBody>
        <DialogFooter>
          <DialogClose render={<Button type="button" variant="outline" disabled={accept.isBusy} />}>
            Not now
          </DialogClose>
          <Button
            state={accept.state}
            loadingLabel="Saving…"
            successLabel="Accepted"
            errorLabel="Not saved"
            onClick={() => {
              void accept.run();
            }}
          >
            I agree
          </Button>
        </DialogFooter>
      </div>
    );
  }

  return (
    <form
      noValidate
      aria-label="Check in"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setProblem(null);
        setOpenVisit(null);
        if (!chosen) {
          setProblem(
            target === "place"
              ? "Name the place."
              : `Pick the ${target === "lead" ? "lead" : "dealer"}.`,
          );
          return;
        }
        void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Check in</DialogTitle>
        <DialogDescription>Where you are now, and who you&apos;re visiting.</DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {openVisit === null ? null : (
          <Notice tone="warning">
            <span role="alert" className="flex flex-col items-start gap-2">
              You&apos;re still checked in at another visit. Check out of it first.
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  onOpenVisit(openVisit);
                }}
              >
                Open that visit
              </Button>
            </span>
          </Notice>
        )}
        <Field>
          <FieldLabel id="check-in-target-label">Visiting</FieldLabel>
          <ToggleGroup
            aria-labelledby="check-in-target-label"
            value={[target]}
            onValueChange={(next) => {
              const picked = TARGETS.find((value) => value === next[0]);
              if (picked !== undefined) {
                setTarget(picked);
                setProblem(null);
              }
            }}
            className="w-full"
          >
            {TARGETS.map((value) => (
              <ToggleGroupItem key={value} value={value} className="flex-1">
                {TARGET_LABELS[value]}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </Field>
        <Field data-invalid={problem === null ? undefined : true}>
          {target === "lead" ? (
            <>
              <FieldLabel htmlFor="check-in-lead">Lead</FieldLabel>
              <VisitLeadPicker
                id="check-in-lead"
                value={lead}
                onValueChange={setLead}
                invalid={problem !== null}
              />
            </>
          ) : target === "dealer" ? (
            <>
              <FieldLabel htmlFor="check-in-dealer">Dealer</FieldLabel>
              <DealerPicker id="check-in-dealer" value={dealer} onValueChange={setDealer} />
            </>
          ) : (
            <>
              <FieldLabel htmlFor="check-in-place">Place</FieldLabel>
              <Input
                id="check-in-place"
                value={place}
                maxLength={200}
                placeholder="e.g. Taluka panchayat office"
                aria-invalid={problem === null ? undefined : true}
                onChange={(event) => {
                  setPlace(event.target.value);
                }}
              />
            </>
          )}
          <FieldError>{problem ?? undefined}</FieldError>
        </Field>
        <FixPanel state={fix} onLocate={locate} action="check in" />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          disabled={fix.status !== "ready"}
          state={save.state}
          loadingLabel="Checking in…"
          successLabel="Checked in"
          errorLabel="Not checked in"
        >
          Check in
        </Button>
      </DialogFooter>
    </form>
  );
}
