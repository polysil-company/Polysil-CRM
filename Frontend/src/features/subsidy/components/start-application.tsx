"use client";

import { ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { Notice } from "@/components/patterns/notice";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { leadDetailQueryOptions } from "@/features/leads/api/leads.queries";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { useCan } from "@/features/session/hooks/use-session";
import { useCreateApplication } from "@/features/subsidy/api/subsidy-applications.mutations";
import {
  applicationKeys,
  applicationListQueryOptions,
  leadSchemeQueryOptions,
} from "@/features/subsidy/api/subsidy-applications.queries";
import type { LeadScheme } from "@/features/subsidy/api/subsidy-applications.schemas";
import {
  subsidyConfigQueryOptions,
  subsidyCropsQueryOptions,
} from "@/features/subsidy/api/subsidy.queries";
import type { SubsidyCalculation, SystemConfig } from "@/features/subsidy/api/subsidy.schemas";
import type { SubsidyCalculationState } from "@/features/subsidy/hooks/use-subsidy-calculation";
import { cannotStartReason, subsidySystemOf } from "@/features/subsidy/lib/application-labels";
import { emptyDraft, type CalculatorDraft } from "@/features/subsidy/lib/calculator-draft";
import { SYSTEM_LABELS } from "@/features/subsidy/lib/subsidy-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { SubsidyCalculatorSkeleton, SystemCalculator } from "./subsidy-calculator";

const log = createLogger({
  file: "features/subsidy/components/start-application.tsx",
  dataId: "SUBS-004",
});

/** The refusals a start can meet, in words (handover `subsidy-applications-contract.md`). */
/** Shown when the lead's state has no scheme ready for applications. */
const NOT_SET_UP = "Subsidy for this state is not set up yet. Ask an administrator.";

/** Why `GET /subsidy-schemes/for-lead` gave no scheme to use. */
const SCHEME_REFUSALS: Readonly<Record<string, string>> = {
  no_scheme_for_state: NOT_SET_UP,
  territory_without_state_code:
    "The lead's area isn't linked to a state, so no scheme applies to it.",
};

const LEAD_REFUSALS: Readonly<Record<string, string>> = {
  scheme_changed:
    "The state's subsidy scheme changed meanwhile. The page has reloaded it: check the figures and start again.",
  no_scheme_for_state: NOT_SET_UP,
  lead_not_subsidised: "This lead isn't a subsidised enquiry.",
  lead_not_forwardable: "The lead needs to be qualified, quoted, in negotiation or won.",
  lead_system_not_subsidised: "The lead's irrigation system has no subsidy calculation.",
  already_forwarded: "This lead already has an application in progress.",
};

/**
 * SUBS-004 · Start a subsidy application from a lead: the calculator for the lead's system,
 * then the farmer's category — only those that apply on every crop — and the survey number.
 * The backend runs the calculation again, stores it, and moves the lead to won.
 */
export function StartApplication({ leadId }: { leadId: string | null }): React.JSX.Element {
  const lead = useQuery({ ...leadDetailQueryOptions(leadId ?? ""), enabled: leadId !== null });
  // The lead's state decides the scheme; the calculator then reads that scheme's masters.
  const scheme = useQuery({ ...leadSchemeQueryOptions(leadId ?? ""), enabled: leadId !== null });
  const schemeBlocked =
    scheme.status === "error" &&
    isApiError(scheme.error) &&
    scheme.error.code !== undefined &&
    SCHEME_REFUSALS[scheme.error.code] !== undefined
      ? (SCHEME_REFUSALS[scheme.error.code] ?? null)
      : scheme.data?.ready === false
        ? NOT_SET_UP
        : null;
  const usable = scheme.data !== undefined && scheme.data.ready;
  const config = useQuery({
    ...subsidyConfigQueryOptions(scheme.data?.code ?? null),
    enabled: usable,
  });

  if (leadId === null) {
    return (
      <Notice tone="info">
        <p>
          An application starts from a subsidised lead: open the lead, then “Start subsidy
          application”.
        </p>
      </Notice>
    );
  }
  if (lead.status === "pending" || (scheme.status === "pending" && schemeBlocked === null)) {
    return <SubsidyCalculatorSkeleton />;
  }
  if (lead.status === "error") {
    return (
      <ErrorState
        error={lead.error}
        onRetry={() => {
          void lead.refetch();
        }}
      />
    );
  }
  if (schemeBlocked !== null || scheme.status === "error") {
    return (
      <StartForLead
        lead={lead.data}
        scheme={null}
        system={null}
        parameters={{}}
        blocked={schemeBlocked ?? toUserFacingError(scheme.error).title}
      />
    );
  }
  if (config.status === "pending") return <SubsidyCalculatorSkeleton />;
  if (config.status === "error") {
    return (
      <ErrorState
        error={config.error}
        onRetry={() => {
          void config.refetch();
        }}
      />
    );
  }
  const system = config.data.systems.find((item) => item.systemType === subsidySystemOf(lead.data));
  return (
    <StartForLead
      lead={lead.data}
      scheme={scheme.data ?? null}
      system={system ?? null}
      parameters={config.data.parameters}
      blocked={null}
    />
  );
}

function StartForLead({
  lead,
  scheme,
  system,
  parameters,
  blocked: schemeBlocked,
}: {
  lead: Lead;
  /** The lead's scheme; null when it has none to use. */
  scheme: LeadScheme | null;
  system: SystemConfig | null;
  parameters: Readonly<Record<string, string>>;
  /** Why the lead's scheme can't take an application, when it can't. */
  blocked: string | null;
}): React.JSX.Element {
  const canCreate = useCan("subsidy", "create");
  const canEdit = useCan("subsidy", "edit");
  const crops = useQuery({
    ...subsidyCropsQueryOptions(scheme?.code ?? null),
    enabled: scheme !== null,
  });
  const existing = useInfiniteQuery(
    applicationListQueryOptions({ status: null, stage: null, q: "", leadId: lead.id }),
  );
  const live = existing.data?.pages
    .flatMap((page) => page.items)
    .find((item) => item.status !== "cancelled");
  const [draft, setDraft] = useState<CalculatorDraft>(() =>
    emptyDraft(system?.systemType ?? "drip"),
  );
  const reason = cannotStartReason(lead);

  const header = (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Link
        href={`/leads/${lead.id}`}
        transitionTypes={["nav-back"]}
        className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
      >
        <Icon icon={ArrowLeft01Icon} size="sm" />
        {lead.customerName}
      </Link>
      <h2 className="text-xl font-semibold text-foreground">Start a subsidy application</h2>
      <p className="text-sm text-muted-foreground">
        <span className="font-mono">{lead.code}</span>
        {system === null ? "" : ` · ${SYSTEM_LABELS[system.systemType]}`}
        {scheme === null ? "" : ` · ${scheme.name}`} · Starting moves the lead to won.
      </p>
    </div>
  );

  // The lead's own reason first; then the scheme's; then the system's tables.
  const blocked = !(canCreate || canEdit)
    ? "You can view applications but not start one."
    : (reason ??
      schemeBlocked ??
      (system === null ? "The scheme has no tables in force for this system." : null));

  if (blocked !== null || system === null) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <Notice tone="info">
          <p>{blocked}</p>
        </Notice>
      </div>
    );
  }
  if (live !== undefined) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <Notice tone="info">
          <p>This lead already has application {live.number}. Cancel it first to start again.</p>
          <Link
            href={`/subsidy/${live.id}`}
            className={buttonVariants({ variant: "outline", size: "sm", className: "self-start" })}
          >
            Open {live.number}
          </Link>
        </Notice>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {header}
      <SystemCalculator
        scheme={scheme?.code ?? null}
        system={system}
        parameters={parameters}
        catalogue={crops.data ?? []}
        cropsFailed={crops.isError}
        onRetryCrops={() => {
          void crops.refetch();
        }}
        draft={draft}
        onDraftChange={setDraft}
        after={(calculation) => <CategoryPick lead={lead} calculation={calculation} />}
      />
    </div>
  );
}

/** Categories that apply on every crop block — the only ones an application may take. */
function applicableEverywhere(
  result: SubsidyCalculation,
): SubsidyCalculation["crops"][number]["categories"] {
  const [first, ...rest] = result.crops;
  if (first === undefined) return [];
  return first.categories.filter(
    (category) =>
      category.applicable &&
      rest.every(
        (crop) => crop.categories.find((row) => row.code === category.code)?.applicable === true,
      ),
  );
}

function CategoryPick({
  lead,
  calculation,
}: {
  lead: Lead;
  calculation: SubsidyCalculationState;
}): React.JSX.Element {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<string | null>(null);
  const [surveyNo, setSurveyNo] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const create = useCreateApplication();
  const idempotency = useIdempotencyKey();
  const result = calculation.upToDate ? calculation.result : null;
  const options = result === null ? [] : applicableEverywhere(result);
  const chosen = options.find((option) => option.code === category) ?? null;
  const left = result === null ? 0 : (result.crops[0]?.categories.length ?? 0) - options.length;
  const ready = result !== null && calculation.plan.request !== null;
  const categoryError = shown && chosen === null ? "Choose the farmer's category." : null;

  const submit = useAsyncAction({
    action: () => {
      const request = calculation.plan.request;
      if (request === null || chosen === null) throw new Error("Nothing to start");
      const body = {
        lead_id: lead.id,
        category_code: chosen.code,
        calculation: request,
        survey_no: surveyNo.trim() === "" ? null : surveyNo.trim(),
      };
      return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleStartApplication",
    dataId: "SUBS-004",
    onSuccess: (application) => {
      idempotency.reset();
      toast.success(`Application ${application.number} started`, {
        description: `${lead.customerName} is now won, at stage ${String(application.stage.seq)}.`,
      });
      router.push(`/subsidy/${application.id}`);
    },
    onError: (error) => {
      if (isApiError(error) && error.code === "scheme_changed") {
        // Read the lead's scheme again; the calculator follows it.
        void queryClient.invalidateQueries({ queryKey: applicationKeys.leadScheme(lead.id) });
      }
      const known =
        isApiError(error) && error.code !== undefined ? LEAD_REFUSALS[error.code] : undefined;
      if (known !== undefined) {
        setRefusal([known]);
        return;
      }
      const fields = readFieldErrors(error);
      if (fields !== null) {
        setRefusal(
          Object.entries(fields).map(([path, message]) =>
            path === "category_code" ? `Category: ${message}` : `${path}: ${message}`,
          ),
        );
        return;
      }
      const view = toUserFacingError(error);
      setRefusal([`${view.title}. ${view.description}`]);
    },
  });

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>The farmer&apos;s category</CardTitle>
          <CardDescription>
            {ready
              ? left > 0
                ? `Only categories that apply on every crop block; ${String(left)} don't.`
                : "Every category applies to this design."
              : "Complete the design to choose a category."}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          aria-label="Start the application"
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            setShown(true);
            setRefusal(null);
            if (!ready || chosen === null) return;
            void submit.run();
          }}
        >
          <Field data-invalid={categoryError === null ? undefined : true}>
            <FieldLabel id="category-label">Category</FieldLabel>
            <RadioGroup<string>
              aria-labelledby="category-label"
              aria-describedby={categoryError === null ? undefined : "category-error"}
              value={chosen?.code ?? ""}
              onValueChange={(next) => {
                setCategory(next);
              }}
              className="flex flex-col gap-2"
            >
              {options.map((option) => (
                <label
                  key={option.code}
                  className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm transition-colors duration-fast has-data-checked:border-primary has-data-checked:bg-primary-soft"
                >
                  <span className="flex items-center gap-2 text-foreground">
                    <RadioGroupItem value={option.code} />
                    {option.name}
                  </span>
                  <span className="text-right text-xs text-muted-foreground tabular-nums">
                    {formatInr(option.subsidy, { paise: true })} subsidy
                  </span>
                </label>
              ))}
            </RadioGroup>
            {ready && options.length === 0 ? (
              <FieldDescription>
                No category applies on every crop block. Change the design.
              </FieldDescription>
            ) : null}
            <FieldError id="category-error">{categoryError}</FieldError>
          </Field>
          <Field>
            <FieldLabel htmlFor="survey-no">
              Survey No.
              <span className="font-normal text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Input
              id="survey-no"
              maxLength={100}
              autoComplete="off"
              placeholder="112/2"
              value={surveyNo}
              onChange={(event) => {
                setSurveyNo(event.target.value);
              }}
            />
          </Field>
          {refusal === null ? null : (
            <div
              role="alert"
              className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
            >
              <p className="font-medium text-danger">The application wasn&apos;t started</p>
              {refusal.map((line) => (
                <p key={line} className="text-foreground">
                  {line}
                </p>
              ))}
            </div>
          )}
          <Button
            type="submit"
            className="self-start"
            disabled={!ready || options.length === 0}
            state={submit.state}
            loadingLabel="Starting…"
            successLabel="Started"
            errorLabel="Not started"
          >
            Start application
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
