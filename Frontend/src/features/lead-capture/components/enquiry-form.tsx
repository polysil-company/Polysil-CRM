"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { CheckmarkCircle02Icon, PencilEdit02Icon, WhatsappIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState, useWatch } from "react-hook-form";
import { z } from "zod";

import { ErrorState } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { OtpInput } from "@/components/ui/otp-input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { sendEnquiryCode, submitEnquiry } from "@/features/lead-capture/api/lead-capture.api";
import {
  publicLeadFormQueryOptions,
  publicTerritoriesQueryOptions,
} from "@/features/lead-capture/api/lead-capture.queries";
import type {
  PublicLeadForm,
  PublicLeadRequest,
  PublicLeadResult,
} from "@/features/lead-capture/api/lead-capture.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useSecondsUntil } from "@/hooks/use-seconds-until";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import {
  describeCountdown,
  formatCountdown,
  formatIndianPhone,
  normalizeIndianMobile,
} from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

const log = createLogger({
  file: "features/lead-capture/components/enquiry-form.tsx",
  dataId: "LEAD-014",
});

const CODE_LENGTH = 6;

const INQUIRY_TYPE_LABELS: Readonly<Record<PublicLeadRequest["inquiry_type"], string>> = {
  commercial: "Buying it myself",
  subsidised: "With a government subsidy",
  industrial: "For a business or factory",
};

const INQUIRY_TYPES = ["commercial", "subsidised", "industrial"] as const;

function isNotFound(error: unknown): boolean {
  return isApiError(error) && error.status === 404;
}

/**
 * LEAD-014 · The public enquiry page (`/enquiry`, `/enquiry?qr=CODE`): no sign-in, read on a
 * phone after scanning a printed code. The farmer says who they are, where, and what they
 * want; the mobile is checked with a six-digit WhatsApp code; then the page shows their
 * inquiry number, which they keep. A code no longer in use still opens the plain form.
 */
export function EnquiryPage({ qr }: { qr: string | null }): React.JSX.Element {
  const withCode = useQuery(publicLeadFormQueryOptions(qr));
  const codeGone = qr !== null && withCode.isError && isNotFound(withCode.error);
  const plain = useQuery({ ...publicLeadFormQueryOptions(null), enabled: codeGone });
  const query = codeGone ? plain : withCode;

  if (query.isPending) return <EnquirySkeleton />;
  if (query.isError) {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return <EnquiryFlow form={query.data} codeGone={codeGone} />;
}

const detailsSchema = z.object({
  farmerName: z.string().trim().min(1, "Enter your name.").max(200, "Keep it under 200 letters."),
  mobile: z
    .string()
    .trim()
    .refine((value) => normalizeIndianMobile(value) !== null, "Enter your 10-digit mobile number."),
  stateId: z.string(),
  districtId: z.string(),
  talukaId: z.string(),
  useCodeArea: z.boolean(),
  village: z.string().trim().max(120, "Keep it under 120 letters."),
  system: z.string().min(1, "Choose what you are interested in."),
  inquiryType: z.enum(INQUIRY_TYPES),
  note: z.string().trim().max(1000, "Keep it under 1,000 letters."),
});

type Details = z.infer<typeof detailsSchema>;

function detailsSchemaFor(hasCodeArea: boolean): z.ZodType<Details, Details> {
  return detailsSchema.superRefine((values, ctx) => {
    const usesCode = hasCodeArea && values.useCodeArea;
    if (!usesCode && values.districtId === "") {
      ctx.addIssue({ code: "custom", path: ["districtId"], message: "Choose your district." });
    }
  });
}

type Step =
  | { readonly kind: "details" }
  | {
      readonly kind: "code";
      readonly details: Details;
      readonly expiresAt: number;
      readonly resendAt: number;
    }
  | { readonly kind: "done"; readonly result: PublicLeadResult };

function EnquiryFlow({
  form: setup,
  codeGone,
}: {
  form: PublicLeadForm;
  codeGone: boolean;
}): React.JSX.Element {
  const [step, setStep] = useState<Step>({ kind: "details" });
  const codeArea = setup.qr?.territoryId ?? null;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        {setup.qr === null ? null : (
          <p className="w-fit rounded-full bg-primary-soft px-3 py-1 text-xs font-medium text-primary-text">
            Enquiry through {setup.qr.label}
          </p>
        )}
        <h1 className="text-2xl font-semibold text-balance text-foreground">
          {step.kind === "done" ? "Thank you" : "Ask about drip and sprinkler irrigation"}
        </h1>
        {step.kind === "done" ? null : (
          <p className="text-sm text-muted-foreground">
            Tell us where your farm is. Our officer for your area calls you back.
          </p>
        )}
      </div>

      {codeGone && step.kind === "details" ? (
        <p role="note" className="rounded-md bg-muted p-3 text-sm text-muted-foreground">
          The code you scanned isn&apos;t in use any more. You can still send your enquiry here.
        </p>
      ) : null}

      {step.kind === "details" ? (
        <DetailsStep
          setup={setup}
          codeArea={codeArea}
          onSent={(details, expiresIn, resendAfter) => {
            const now = Date.now();
            setStep({
              kind: "code",
              details,
              expiresAt: now + expiresIn * 1000,
              resendAt: now + resendAfter * 1000,
            });
          }}
        />
      ) : null}
      {step.kind === "code" ? (
        <CodeStep
          step={step}
          qr={setup.qr?.code ?? null}
          codeArea={codeArea}
          onRenewed={(expiresIn, resendAfter) => {
            const now = Date.now();
            setStep({
              ...step,
              expiresAt: now + expiresIn * 1000,
              resendAt: now + resendAfter * 1000,
            });
          }}
          onBack={() => {
            setStep({ kind: "details" });
          }}
          onDone={(result) => {
            setStep({ kind: "done", result });
          }}
        />
      ) : null}
      {step.kind === "done" ? <DoneStep result={step.result} /> : null}
    </div>
  );
}

function DetailsStep({
  setup,
  codeArea,
  onSent,
}: {
  setup: PublicLeadForm;
  codeArea: string | null;
  onSent: (details: Details, expiresIn: number, resendAfter: number) => void;
}): React.JSX.Element {
  const onlyState = setup.states.length === 1 ? (setup.states[0]?.id ?? "") : "";
  const form = useForm<Details>({
    resolver: zodResolver(detailsSchemaFor(codeArea !== null)),
    defaultValues: {
      farmerName: "",
      mobile: "",
      stateId: onlyState,
      districtId: "",
      talukaId: "",
      useCodeArea: codeArea !== null,
      village: "",
      system: "",
      inquiryType: "commercial",
      note: "",
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const [stateId, districtId, useCodeArea] = useWatch({
    control: form.control,
    name: ["stateId", "districtId", "useCodeArea"],
  });
  const districts = useQuery(publicTerritoriesQueryOptions(stateId));
  const talukas = useQuery(publicTerritoriesQueryOptions(districtId));
  const [refusal, setRefusal] = useState<string | null>(null);
  const showPickers = codeArea === null || !useCodeArea;

  const send = useAsyncAction({
    action: (values: Details) => sendEnquiryCode(values.mobile),
    logger: log,
    fn: "handleSendEnquiryCode",
    dataId: "LEAD-014",
    onSuccess: (sent) => {
      onSent(form.getValues(), sent.expiresIn, sent.resendAfter);
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.status === 429
          ? "Too many codes were sent to this number. Wait a while, then try again."
          : toUserFacingError(error).description,
      );
    },
  });

  const items = (
    rows: readonly { id: string; name: string }[],
  ): { value: string; label: string }[] => rows.map((row) => ({ value: row.id, label: row.name }));

  return (
    <form
      noValidate
      aria-label="Your enquiry"
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => send.run(values))(event);
      }}
    >
      <FieldGroup className="flex flex-col gap-4">
        <Field data-invalid={errors.farmerName ? true : undefined}>
          <FieldLabel htmlFor="enquiry-name">Your name</FieldLabel>
          <Input
            id="enquiry-name"
            autoComplete="name"
            aria-invalid={errors.farmerName ? true : undefined}
            aria-describedby={errors.farmerName ? "enquiry-name-error" : undefined}
            {...form.register("farmerName")}
          />
          <FieldError id="enquiry-name-error">{errors.farmerName?.message}</FieldError>
        </Field>
        <Field data-invalid={errors.mobile ? true : undefined}>
          <FieldLabel htmlFor="enquiry-mobile">Mobile number</FieldLabel>
          <Input
            id="enquiry-mobile"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            placeholder="98765 43210"
            aria-invalid={errors.mobile ? true : undefined}
            aria-describedby={errors.mobile ? "enquiry-mobile-error" : "enquiry-mobile-hint"}
            {...form.register("mobile")}
          />
          {errors.mobile ? null : (
            <FieldDescription id="enquiry-mobile-hint">
              We send a code to this number on WhatsApp.
            </FieldDescription>
          )}
          <FieldError id="enquiry-mobile-error">{errors.mobile?.message}</FieldError>
        </Field>

        {codeArea !== null && useCodeArea ? (
          <div className="flex flex-col gap-1 rounded-md bg-muted p-3 text-sm">
            <p className="text-foreground">Your area comes from the code you scanned.</p>
            <Button
              type="button"
              variant="link"
              size="sm"
              className="self-start px-0"
              onClick={() => {
                form.setValue("useCodeArea", false);
              }}
            >
              Choose another area
            </Button>
          </div>
        ) : null}

        {showPickers ? (
          <>
            {setup.states.length > 1 ? (
              <Controller
                control={form.control}
                name="stateId"
                render={({ field }) => (
                  <Field>
                    <FieldLabel htmlFor="enquiry-state">State</FieldLabel>
                    <Select
                      items={items(setup.states)}
                      value={field.value === "" ? null : field.value}
                      onValueChange={(next) => {
                        if (typeof next === "string") {
                          field.onChange(next);
                          form.setValue("districtId", "");
                          form.setValue("talukaId", "");
                        }
                      }}
                    >
                      <SelectTrigger id="enquiry-state">
                        <SelectValue placeholder="Choose your state" />
                      </SelectTrigger>
                      <SelectContent>
                        {setup.states.map((row) => (
                          <SelectItem key={row.id} value={row.id}>
                            {row.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                )}
              />
            ) : null}
            <div className="grid gap-4 sm:grid-cols-2">
              <Controller
                control={form.control}
                name="districtId"
                render={({ field, fieldState }) => (
                  <Field data-invalid={fieldState.error ? true : undefined}>
                    <FieldLabel htmlFor="enquiry-district">District</FieldLabel>
                    <Select
                      items={items(districts.data ?? [])}
                      value={field.value === "" ? null : field.value}
                      disabled={stateId === "" || districts.isPending}
                      onValueChange={(next) => {
                        if (typeof next === "string") {
                          field.onChange(next);
                          form.setValue("talukaId", "");
                        }
                      }}
                    >
                      <SelectTrigger
                        id="enquiry-district"
                        aria-invalid={fieldState.error ? true : undefined}
                        aria-describedby={fieldState.error ? "enquiry-district-error" : undefined}
                      >
                        <SelectValue
                          placeholder={districts.isPending ? "Loading…" : "Choose your district"}
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {(districts.data ?? []).map((row) => (
                          <SelectItem key={row.id} value={row.id}>
                            {row.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FieldError id="enquiry-district-error">{fieldState.error?.message}</FieldError>
                  </Field>
                )}
              />
              <Controller
                control={form.control}
                name="talukaId"
                render={({ field }) => (
                  <Field>
                    <FieldLabel htmlFor="enquiry-taluka">
                      Taluka
                      <span className="font-normal text-subtle-foreground">(optional)</span>
                    </FieldLabel>
                    <Select
                      items={items(talukas.data ?? [])}
                      value={field.value === "" ? null : field.value}
                      disabled={districtId === "" || talukas.isPending}
                      onValueChange={(next) => {
                        if (typeof next === "string") field.onChange(next);
                      }}
                    >
                      <SelectTrigger id="enquiry-taluka">
                        <SelectValue placeholder="Choose your taluka" />
                      </SelectTrigger>
                      <SelectContent>
                        {(talukas.data ?? []).map((row) => (
                          <SelectItem key={row.id} value={row.id}>
                            {row.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                )}
              />
            </div>
          </>
        ) : null}

        <Field data-invalid={errors.village ? true : undefined}>
          <FieldLabel htmlFor="enquiry-village">
            Village
            <span className="font-normal text-subtle-foreground">(optional)</span>
          </FieldLabel>
          <Input
            id="enquiry-village"
            autoComplete="address-level3"
            aria-invalid={errors.village ? true : undefined}
            aria-describedby={errors.village ? "enquiry-village-error" : undefined}
            {...form.register("village")}
          />
          <FieldError id="enquiry-village-error">{errors.village?.message}</FieldError>
        </Field>

        <Controller
          control={form.control}
          name="system"
          render={({ field, fieldState }) => (
            <Field data-invalid={fieldState.error ? true : undefined}>
              <FieldLabel id="enquiry-system-label">What are you interested in?</FieldLabel>
              <RadioGroup<string>
                aria-labelledby="enquiry-system-label"
                aria-describedby={fieldState.error ? "enquiry-system-error" : undefined}
                value={field.value}
                onValueChange={field.onChange}
                className="grid grid-cols-2 gap-2"
              >
                {setup.systems.map((system) => (
                  <label
                    key={system.code}
                    className="flex min-h-control-lg items-center gap-2 rounded-md border border-border px-3 text-sm text-foreground"
                  >
                    <RadioGroupItem value={system.code} />
                    {system.name}
                  </label>
                ))}
              </RadioGroup>
              <FieldError id="enquiry-system-error">{fieldState.error?.message}</FieldError>
            </Field>
          )}
        />

        <Controller
          control={form.control}
          name="inquiryType"
          render={({ field }) => (
            <Field>
              <FieldLabel id="enquiry-type-label">How will you buy it?</FieldLabel>
              <RadioGroup<(typeof INQUIRY_TYPES)[number]>
                aria-labelledby="enquiry-type-label"
                value={field.value}
                onValueChange={field.onChange}
                className="flex flex-col gap-2"
              >
                {INQUIRY_TYPES.filter((type) => setup.inquiryTypes.includes(type)).map((type) => (
                  <label key={type} className="flex items-center gap-2 text-sm text-foreground">
                    <RadioGroupItem value={type} />
                    {INQUIRY_TYPE_LABELS[type]}
                  </label>
                ))}
              </RadioGroup>
            </Field>
          )}
        />

        <Field data-invalid={errors.note ? true : undefined}>
          <FieldLabel htmlFor="enquiry-note">
            Anything else
            <span className="font-normal text-subtle-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="enquiry-note"
            rows={3}
            placeholder="Crop, land size, a good time to call…"
            aria-invalid={errors.note ? true : undefined}
            aria-describedby={errors.note ? "enquiry-note-error" : undefined}
            {...form.register("note")}
          />
          <FieldError id="enquiry-note-error">{errors.note?.message}</FieldError>
        </Field>
      </FieldGroup>

      {refusal === null ? null : (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
          {refusal}
        </p>
      )}

      <Button
        type="submit"
        size="lg"
        className="w-full"
        state={send.state}
        loadingLabel="Sending the code…"
        successLabel="Code sent"
        errorLabel="Not sent"
      >
        <Icon icon={WhatsappIcon} />
        Send me a code on WhatsApp
      </Button>
    </form>
  );
}

function CodeStep({
  step,
  qr,
  codeArea,
  onRenewed,
  onBack,
  onDone,
}: {
  step: Extract<Step, { kind: "code" }>;
  qr: string | null;
  codeArea: string | null;
  onRenewed: (expiresIn: number, resendAfter: number) => void;
  onBack: () => void;
  onDone: (result: PublicLeadResult) => void;
}): React.JSX.Element {
  const { details } = step;
  const [code, setCode] = useState("");
  const [refusal, setRefusal] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const expiresIn = useSecondsUntil(step.expiresAt) ?? 0;
  const resendIn = useSecondsUntil(step.resendAt) ?? 0;
  const expired = expiresIn === 0;

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const territoryId =
    codeArea !== null && details.useCodeArea
      ? codeArea
      : details.talukaId !== ""
        ? details.talukaId
        : details.districtId;

  const submit = useAsyncAction({
    action: (value: string) =>
      submitEnquiry({
        mobile: details.mobile,
        code: value,
        farmer_name: details.farmerName.trim(),
        territory_id: territoryId,
        village: details.village.trim() === "" ? null : details.village.trim(),
        mis_system: details.system,
        inquiry_type: details.inquiryType,
        note: details.note.trim() === "" ? null : details.note.trim(),
        qr,
      }),
    logger: log,
    fn: "handleSubmitEnquiry",
    dataId: "LEAD-014",
    onSuccess: onDone,
    onError: (error) => {
      setCode("");
      inputRef.current?.focus();
      if (isApiError(error) && error.code === "invalid_code") {
        setRefusal("That code doesn't match, or it has expired. Check it, or send a new one.");
      } else if (readFieldErrors(error)?.territory_id !== undefined) {
        setRefusal("Choose your district or taluka again: go back and change it.");
      } else {
        setRefusal(toUserFacingError(error).description);
      }
    },
  });

  const resend = useAsyncAction({
    action: () => sendEnquiryCode(details.mobile),
    logger: log,
    fn: "handleResendEnquiryCode",
    dataId: "LEAD-014",
    onSuccess: (sent) => {
      setRefusal(null);
      setCode("");
      onRenewed(sent.expiresIn, sent.resendAfter);
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.status === 429
          ? "Too many codes were sent to this number. Wait a while, then try again."
          : toUserFacingError(error).description,
      );
    },
  });

  const go = (value: string): void => {
    if (value.length !== CODE_LENGTH || expired || submit.isBusy) return;
    setRefusal(null);
    void submit.run(value);
  };

  return (
    <form
      noValidate
      aria-label="Enter the code from WhatsApp"
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        event.preventDefault();
        go(code);
      }}
    >
      <div className="flex flex-col items-start gap-1">
        <p className="text-sm text-muted-foreground">
          We sent a {CODE_LENGTH}-digit code on WhatsApp to{" "}
          <span className="font-medium whitespace-nowrap text-foreground tabular-nums">
            {formatIndianPhone(details.mobile)}
          </span>
          .
        </p>
        <Button type="button" variant="link" size="sm" className="px-0" onClick={onBack}>
          <Icon icon={PencilEdit02Icon} />
          Change my details
        </Button>
      </div>

      <Field data-invalid={refusal !== null ? true : undefined}>
        <FieldLabel htmlFor="enquiry-code">{CODE_LENGTH}-digit code</FieldLabel>
        <OtpInput
          ref={inputRef}
          id="enquiry-code"
          length={CODE_LENGTH}
          value={code}
          readOnly={submit.isBusy}
          disabled={expired}
          aria-describedby="enquiry-code-status"
          onValueChange={setCode}
          onComplete={go}
        />
        <p
          id="enquiry-code-status"
          className={cn("text-xs/normal", expired ? "text-warning" : "text-muted-foreground")}
        >
          {expired ? (
            "This code has expired. Send a new one."
          ) : (
            <>
              The code works for{" "}
              <span aria-hidden="true" className="tabular-nums">
                {formatCountdown(expiresIn)}
              </span>
              <span className="sr-only">{describeCountdown(expiresIn)}</span>
            </>
          )}
        </p>
      </Field>

      {refusal === null ? null : (
        <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
          {refusal}
        </p>
      )}

      <Button
        type="submit"
        size="lg"
        className="w-full"
        state={submit.state}
        disabled={code.length !== CODE_LENGTH || expired}
        loadingLabel="Sending…"
        successLabel="Sent"
        errorLabel="Not sent"
      >
        Send my enquiry
      </Button>

      <div className="flex min-h-control-sm items-center justify-center text-center text-sm text-muted-foreground">
        {resendIn > 0 ? (
          <p>
            No code? Ask for another in{" "}
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

function DoneStep({ result }: { result: PublicLeadResult }): React.JSX.Element {
  return (
    <section
      aria-label="Your enquiry number"
      className="flex flex-col items-start gap-4 rounded-xl border border-border bg-card p-5"
    >
      <Icon icon={CheckmarkCircle02Icon} size="xl" className="text-success" />
      <div className="flex flex-col gap-1">
        <p className="text-sm text-muted-foreground">
          {result.created
            ? "Your enquiry is with us. Your number is"
            : "You already sent an enquiry today. Your number is"}
        </p>
        <p className="font-mono text-xl font-semibold text-foreground sm:text-2xl">
          {result.inquiryNo}
        </p>
      </div>
      <p className="text-sm text-muted-foreground">
        Keep this number: quote it when our officer calls. We also send it on WhatsApp, but that
        message can be held back if we already wrote to you today, so this page is the place to read
        it.
      </p>
    </section>
  );
}

export function EnquirySkeleton(): React.JSX.Element {
  return (
    <div role="status" aria-label="Loading the enquiry form" className="flex flex-col gap-4">
      <Skeleton className="h-8 w-3/4" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-10 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
