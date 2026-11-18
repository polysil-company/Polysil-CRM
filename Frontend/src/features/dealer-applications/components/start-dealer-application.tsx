"use client";

import Link from "next/link";
import { useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  PARTNER_TYPES,
  type PartnerType,
} from "@/features/dealer-applications/api/data-sheet.schemas";
import { useCreateDealerApplication } from "@/features/dealer-applications/api/dealer-applications.mutations";
import type { DealerApplication } from "@/features/dealer-applications/api/dealer-applications.schemas";
import { PARTNER_TYPE_LABELS } from "@/features/dealer-applications/lib/dealer-application-labels";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { normalizeIndianMobile } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { ApplyLink } from "./apply-link";
import { RefusalNote, type Refusal } from "./dealer-application-refusals";

const log = createLogger({
  file: "features/dealer-applications/components/start-dealer-application.tsx",
  dataId: "CHNL-007",
});

type Field = "firm_name" | "contact_name" | "mobile" | "territory_id";

/**
 * CHNL-007 · Start an application: a dealer or a distributor (FS-071), the firm, whom to ask
 * for, the mobile that becomes its login, and the area. Then the link to send them, shown only
 * now. The type's deposit is fixed when it starts.
 */
export function StartDealerApplication({ onClose }: { onClose: () => void }): React.JSX.Element {
  const create = useCreateDealerApplication();
  const idempotency = useIdempotencyKey();
  const [partnerType, setPartnerType] = useState<PartnerType>("dealer");
  const [firm, setFirm] = useState("");
  const [contact, setContact] = useState("");
  const [mobile, setMobile] = useState("");
  const [territory, setTerritory] = useState<TerritoryChoice | null>(null);
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<Partial<Record<Field, string>>>({});
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const [started, setStarted] = useState<DealerApplication | null>(null);

  const local: Partial<Record<Field, string>> = {};
  if (firm.trim() === "") local.firm_name = "Enter the firm's name.";
  if (contact.trim() === "") local.contact_name = "Enter whom to ask for.";
  if (normalizeIndianMobile(mobile) === null) {
    local.mobile = "Enter a 10-digit Indian mobile number.";
  }
  if (territory === null) local.territory_id = "Choose the area.";
  const problems: Partial<Record<Field, string>> = { ...(shown ? local : {}), ...server };

  const submit = useAsyncAction({
    action: () => {
      const body = {
        firm_name: firm.trim(),
        contact_name: contact.trim(),
        mobile: normalizeIndianMobile(mobile) ?? mobile.trim(),
        territory_id: territory?.id ?? "",
        partner_type: partnerType,
      };
      return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleStartDealerApplication",
    dataId: "CHNL-007",
    onSuccess: (application) => {
      idempotency.reset();
      setStarted(application);
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "mobile_in_use") {
        setServer({ mobile: "This mobile already signs in a colleague or a partner." });
        return;
      }
      if (isApiError(error) && error.code === "application_open") {
        setServer({ mobile: "An open application already has this mobile." });
        return;
      }
      const fields = readFieldErrors(error);
      if (fields !== null) {
        const mapped: Partial<Record<Field, string>> = {};
        for (const key of ["firm_name", "contact_name", "mobile", "territory_id"] as const) {
          const message = fields[key];
          if (message !== undefined) mapped[key] = message;
        }
        setServer(mapped);
        if (Object.keys(mapped).length > 0) return;
      }
      const view = toUserFacingError(error);
      setRefusal({ title: view.title, message: view.description });
    },
  });

  if (started !== null) {
    return (
      <>
        <DialogHeader>
          <DialogTitle>Application started</DialogTitle>
          <DialogDescription>
            Send {started.contactName} this link to fill in {started.firmName}&apos;s details. It
            works for 30 days.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          {started.applyUrl === null ? (
            <p className="text-sm text-muted-foreground">
              The link didn&apos;t come back. Open the application and make a new link.
            </p>
          ) : (
            <ApplyLink url={started.applyUrl} name={started.contactName} mobile={started.mobile} />
          )}
        </DialogBody>
        <DialogFooter>
          <Link
            href={`/partners/applications/${started.id}`}
            transitionTypes={["nav-forward"]}
            className={buttonVariants({ variant: "outline" })}
            onClick={onClose}
          >
            Open the application
          </Link>
          <DialogClose render={<Button type="button" />}>Done</DialogClose>
        </DialogFooter>
      </>
    );
  }

  return (
    <form
      noValidate
      aria-label="Start an application"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServer({});
        setRefusal(null);
        if (Object.keys(local).length > 0) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Start an application</DialogTitle>
        <DialogDescription>
          The applicant gets a link to fill in the rest. Their mobile becomes the partner&apos;s
          login once approved.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field>
          <FieldLabel id="dealer-app-type-label">For a new</FieldLabel>
          <RadioGroup<PartnerType>
            aria-labelledby="dealer-app-type-label"
            value={partnerType}
            onValueChange={setPartnerType}
            className="flex-row flex-wrap gap-5"
          >
            {PARTNER_TYPES.map((type) => (
              <label key={type} className="flex items-center gap-2 text-sm text-foreground">
                <RadioGroupItem value={type} />
                {PARTNER_TYPE_LABELS[type]}
              </label>
            ))}
          </RadioGroup>
        </Field>
        <TextInput
          id="dealer-app-firm"
          label="Firm"
          value={firm}
          error={problems.firm_name}
          autoComplete="organization"
          onChange={setFirm}
        />
        <TextInput
          id="dealer-app-contact"
          label="Contact person"
          value={contact}
          error={problems.contact_name}
          autoComplete="name"
          onChange={setContact}
        />
        <TextInput
          id="dealer-app-mobile"
          label="Mobile"
          value={mobile}
          error={problems.mobile}
          autoComplete="tel"
          inputMode="tel"
          description="The link goes here, and it becomes the partner's login."
          onChange={(next) => {
            setMobile(next);
            setServer(({ mobile: _mobile, ...rest }) => rest);
          }}
        />
        <Field data-invalid={problems.territory_id === undefined ? undefined : true}>
          <FieldLabel htmlFor="dealer-app-territory">Area</FieldLabel>
          <TerritoryPicker
            id="dealer-app-territory"
            value={territory}
            onValueChange={setTerritory}
            aria-invalid={problems.territory_id === undefined ? undefined : true}
            aria-describedby={
              problems.territory_id === undefined ? undefined : "dealer-app-territory-error"
            }
          />
          <FieldError id="dealer-app-territory-error">{problems.territory_id}</FieldError>
        </Field>
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Starting…"
          successLabel="Started"
          errorLabel="Not started"
        >
          Start the application
        </Button>
      </DialogFooter>
    </form>
  );
}

function TextInput({
  id,
  label,
  value,
  error,
  description,
  autoComplete,
  inputMode,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  error: string | undefined;
  description?: string;
  autoComplete?: string;
  inputMode?: "tel";
  onChange: (next: string) => void;
}): React.JSX.Element {
  const describedBy = error !== undefined ? `${id}-error` : description ? `${id}-hint` : undefined;
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Input
        id={id}
        value={value}
        autoComplete={autoComplete}
        inputMode={inputMode}
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      {description !== undefined && error === undefined ? (
        <FieldDescription id={`${id}-hint`}>{description}</FieldDescription>
      ) : null}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}
