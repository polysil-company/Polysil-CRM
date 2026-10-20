"use client";

import { ArrowLeft01Icon, Calculator01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { notFound, useRouter } from "next/navigation";
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
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Skeleton } from "@/components/ui/skeleton";
import { leadDetailQueryOptions } from "@/features/leads/api/leads.queries";
import { useSetQuotationSubsidy } from "@/features/quotations/api/quotations.mutations";
import {
  quotationDetailQueryOptions,
  quotationSubsidyCalculationQueryOptions,
} from "@/features/quotations/api/quotations.queries";
import type { Quotation } from "@/features/quotations/api/quotations.schemas";
import { parseWarnings, quotationTitle } from "@/features/quotations/lib/quotation-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { leadSchemeQueryOptions } from "@/features/subsidy/api/subsidy-applications.queries";
import {
  subsidyConfigQueryOptions,
  subsidyCropsQueryOptions,
} from "@/features/subsidy/api/subsidy.queries";
import type { SystemConfig } from "@/features/subsidy/api/subsidy.schemas";
import { CalculationFigures } from "@/features/subsidy/components/calculator-results";
import {
  SubsidyCalculatorSkeleton,
  SystemCalculator,
} from "@/features/subsidy/components/subsidy-calculator";
import type { SubsidyCalculationState } from "@/features/subsidy/hooks/use-subsidy-calculation";
import { subsidySystemOf } from "@/features/subsidy/lib/application-labels";
import {
  applicableEverywhere,
  emptyDraft,
  type CalculatorDraft,
} from "@/features/subsidy/lib/calculator-draft";
import { SYSTEM_LABELS } from "@/features/subsidy/lib/subsidy-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatFullDate, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/quotations/components/quotation-subsidy.tsx",
  dataId: "QUOT-014",
});

const TOTAL_DIFFERS = "calculation_total_differs";

function isZero(value: string): boolean {
  return /^-?0+(\.0+)?$/.test(value);
}

function systemLabel(code: string): string {
  return code === "drip" || code === "mini_sprinkler" || code === "sprinkler"
    ? SYSTEM_LABELS[code]
    : code;
}

/** The quotation warnings the subsidy card says in its own words; the notices leave them out. */
export function isSubsidyWarning(code: string): boolean {
  return code === TOTAL_DIFFERS;
}

/**
 * QUOT-014 · A subsidised quotation's subsidy (FS-057): what the scheme pays and the farmer
 * pays for its category, from the calculation stored with it. A draft without one can't be
 * sent; the button opens the calculator. The full calculation is read when asked for.
 */
export function QuotationSubsidyCard({ quotation }: { quotation: Quotation }): React.JSX.Element {
  const canEdit = useCan("quotations", "edit");
  const [showFull, setShowFull] = useState(false);
  const { subsidy } = quotation;
  const draft = quotation.status === "draft";
  const differs = parseWarnings(quotation.warnings).some(
    (warning) => warning.code === TOTAL_DIFFERS,
  );
  const calculate =
    draft && canEdit && quotation.lead !== null ? (
      <Link
        href={`/quotations/${quotation.id}/subsidy`}
        className={buttonVariants({
          variant: subsidy === null ? "primary" : "outline",
          size: "sm",
        })}
      >
        <Icon icon={Calculator01Icon} />
        {subsidy === null ? "Calculate the subsidy" : "Recalculate"}
      </Link>
    ) : null;

  return (
    <Card>
      <CardHeader className="flex-wrap">
        <div className="flex flex-col gap-0.5">
          <CardTitle level={3}>Subsidy</CardTitle>
          <CardDescription>
            {subsidy === null
              ? "Not calculated yet. A subsidised quotation is sent with its subsidy."
              : `${subsidy.scheme} · ${systemLabel(subsidy.systemType)} · masters of ${formatFullDate(subsidy.asOf)}`}
          </CardDescription>
        </div>
        {calculate}
      </CardHeader>
      {subsidy === null ? null : (
        <CardContent className="flex flex-col gap-4">
          {differs ? (
            <Notice tone="warning">
              <p>
                The calculation&apos;s total differs from the quotation&apos;s lines. Recalculate if
                the lines changed.
              </p>
            </Notice>
          ) : null}
          <dl className="grid gap-2 sm:grid-cols-3">
            <Figure label="Category">
              {subsidy.category.name}
              <span className="text-xs text-muted-foreground"> · {subsidy.category.pct}%</span>
            </Figure>
            <Figure label="The scheme pays" strong>
              {formatInr(subsidy.subsidy, { paise: true })}
            </Figure>
            <Figure label="The farmer pays" strong>
              {formatInr(subsidy.farmerShare, { paise: true })}
            </Figure>
            <Figure label="Total cost">
              {formatInr(subsidy.totalCost, { paise: true })}
              {isZero(subsidy.flatCharge) ? null : (
                <span className="text-xs text-muted-foreground">
                  {" "}
                  · with {formatInr(subsidy.flatCharge, { paise: true })} inspection outside the cap
                </span>
              )}
            </Figure>
            {isZero(subsidy.gstPaidByState) ? null : (
              <Figure label="GST paid by the state">
                {formatInr(subsidy.gstPaidByState, { paise: true })}
              </Figure>
            )}
          </dl>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="self-start"
            aria-expanded={showFull}
            onClick={() => {
              setShowFull((open) => !open);
            }}
          >
            {showFull ? "Hide the full calculation" : "Show the full calculation"}
          </Button>
          {showFull ? <StoredCalculation quotationId={quotation.id} /> : null}
        </CardContent>
      )}
    </Card>
  );
}

function Figure({
  label,
  strong = false,
  children,
}: {
  label: string;
  strong?: boolean;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 rounded-md border border-border px-3 py-2">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd
        className={
          strong
            ? "text-lg font-semibold text-foreground tabular-nums"
            : "text-sm text-foreground tabular-nums"
        }
      >
        {children}
      </dd>
    </div>
  );
}

function StoredCalculation({ quotationId }: { quotationId: string }): React.JSX.Element {
  const query = useQuery(quotationSubsidyCalculationQueryOptions(quotationId));
  if (query.status === "pending") {
    return (
      <div role="status" aria-label="Loading the calculation" className="flex flex-col gap-2">
        <Skeleton className="h-32 w-full rounded-xl" />
      </div>
    );
  }
  if (query.status === "error") {
    return (
      <ErrorState
        error={query.error}
        onRetry={() => {
          void query.refetch();
        }}
      />
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <CalculationFigures
        result={query.data}
        hasHeadUnit={query.data.systemType !== "sprinkler"}
        parameters={{}}
        stored
      />
    </div>
  );
}

// ── the subsidy step (draft only) ─────────────────────────────────────────────────

/** Why the lead's scheme gives no calculator, in words. */
const SCHEME_REFUSALS: Readonly<Record<string, string>> = {
  no_scheme_for_state: "Subsidy for the lead's state is not set up yet. Ask an administrator.",
  territory_without_state_code:
    "The lead's area isn't linked to a state, so no scheme applies to it.",
};

/** The refusals a save can meet (subsidised-quotations.md). */
const SAVE_REFUSALS: Readonly<Record<string, string>> = {
  not_subsidised: "This quotation isn't subsidised. Change its sales type first.",
  quotation_not_draft: "The quotation was sent meanwhile. Only a draft takes a subsidy.",
  masters_not_in_force: "The scheme's figures for today aren't loaded. Ask an administrator.",
};

/**
 * QUOT-014 · The subsidy step of a subsidised draft: the calculator for the lead's scheme and
 * system, then the farmer's category (only one that applies on every crop block). Saving runs
 * the calculation again on the backend and stores it with the quotation.
 */
export function QuotationSubsidyStep({ quotationId }: { quotationId: string }): React.JSX.Element {
  const quotation = useQuery(quotationDetailQueryOptions(quotationId));
  const leadId = quotation.data?.lead?.id ?? null;
  const lead = useQuery({ ...leadDetailQueryOptions(leadId ?? ""), enabled: leadId !== null });
  const scheme = useQuery({ ...leadSchemeQueryOptions(leadId ?? ""), enabled: leadId !== null });
  const usable = scheme.data !== undefined && scheme.data.ready;
  const config = useQuery({
    ...subsidyConfigQueryOptions(scheme.data?.code ?? null),
    enabled: usable,
  });

  if (quotation.status === "pending") return <SubsidyCalculatorSkeleton />;
  if (quotation.status === "error") {
    if (isApiError(quotation.error) && quotation.error.status === 404) notFound();
    return (
      <ErrorState
        error={quotation.error}
        onRetry={() => {
          void quotation.refetch();
        }}
      />
    );
  }
  const header = <StepHeader quotation={quotation.data} />;
  const blocked = blockedReason(quotation.data);
  if (blocked !== null) return <Blocked header={header} reason={blocked} />;
  if (lead.status === "pending" || scheme.status === "pending") {
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
  if (scheme.status === "error") {
    const code = isApiError(scheme.error) ? scheme.error.code : undefined;
    const reason = code === undefined ? undefined : SCHEME_REFUSALS[code];
    return (
      <Blocked header={header} reason={reason ?? toUserFacingError(scheme.error).description} />
    );
  }
  if (!scheme.data.ready) {
    return (
      <Blocked
        header={header}
        reason="Subsidy for the lead's state is not set up yet. Ask an administrator."
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
  const systemType = subsidySystemOf(lead.data);
  const system = config.data.systems.find((item) => item.systemType === systemType);
  if (systemType === null || system === undefined) {
    return (
      <Blocked
        header={header}
        reason="The lead's irrigation system has no subsidy calculation in this scheme."
      />
    );
  }
  return (
    <StepCalculator
      header={header}
      quotation={quotation.data}
      scheme={scheme.data.code}
      system={system}
      parameters={config.data.parameters}
    />
  );
}

function blockedReason(quotation: Quotation): string | null {
  if (quotation.salesType !== "subsidised") {
    return "This quotation isn't subsidised, so it has no subsidy to calculate.";
  }
  if (quotation.status !== "draft") return "Only a draft's subsidy can be calculated.";
  if (quotation.lead === null) return "The quotation's lead isn't visible to you.";
  return null;
}

function StepHeader({ quotation }: { quotation: Quotation }): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Link
        href={`/quotations/${quotation.id}`}
        transitionTypes={["nav-back"]}
        className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
      >
        <Icon icon={ArrowLeft01Icon} size="sm" />
        {quotationTitle(quotation)}
      </Link>
      <h2 className="text-xl font-semibold text-foreground">The subsidy</h2>
      <p className="text-sm text-muted-foreground">
        For {quotation.party.name}. The figures come from the lead&apos;s scheme; the quotation
        keeps its own lines and prices.
      </p>
    </div>
  );
}

function Blocked({
  header,
  reason,
}: {
  header: React.ReactNode;
  reason: string;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-4">
      {header}
      <Notice tone="info">
        <p>{reason}</p>
      </Notice>
    </div>
  );
}

function StepCalculator({
  header,
  quotation,
  scheme,
  system,
  parameters,
}: {
  header: React.ReactNode;
  quotation: Quotation;
  scheme: string;
  system: SystemConfig;
  parameters: Readonly<Record<string, string>>;
}): React.JSX.Element {
  const crops = useQuery(subsidyCropsQueryOptions(scheme));
  const [draft, setDraft] = useState<CalculatorDraft>(() => emptyDraft(system.systemType));
  return (
    <div className="flex flex-col gap-4">
      {header}
      <SystemCalculator
        scheme={scheme}
        system={system}
        parameters={parameters}
        catalogue={crops.data ?? []}
        cropsFailed={crops.isError}
        onRetryCrops={() => {
          void crops.refetch();
        }}
        draft={draft}
        onDraftChange={setDraft}
        after={(calculation) => <SaveSubsidy quotation={quotation} calculation={calculation} />}
      />
    </div>
  );
}

function SaveSubsidy({
  quotation,
  calculation,
}: {
  quotation: Quotation;
  calculation: SubsidyCalculationState;
}): React.JSX.Element {
  const router = useRouter();
  const save = useSetQuotationSubsidy();
  const idempotency = useIdempotencyKey();
  const [category, setCategory] = useState<string | null>(quotation.subsidy?.category.code ?? null);
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string[] | null>(null);
  const result = calculation.upToDate ? calculation.result : null;
  const options = result === null ? [] : applicableEverywhere(result);
  const chosen = options.find((option) => option.code === category) ?? null;
  const ready = result !== null && calculation.plan.request !== null;
  const categoryError = shown && chosen === null ? "Choose the farmer's category." : null;

  const submit = useAsyncAction({
    action: () => {
      const request = calculation.plan.request;
      if (request === null || chosen === null) throw new Error("Nothing to save");
      // The backend runs it on the lead's scheme; naming it is refused if it differs.
      const { scheme: _scheme, ...rest } = request;
      const body = { category_code: chosen.code, calculation: rest };
      return save.mutateAsync({
        quotationId: quotation.id,
        input: { body, idempotencyKey: idempotency.keyFor(body) },
      });
    },
    logger: log,
    fn: "handleSaveSubsidy",
    dataId: "QUOT-014",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success("Subsidy saved", {
        description:
          saved.subsidy === null
            ? undefined
            : `${formatInr(saved.subsidy.subsidy, { paise: true })} from the scheme; the farmer pays ${formatInr(saved.subsidy.farmerShare, { paise: true })}.`,
      });
      router.push(`/quotations/${quotation.id}`);
    },
    onError: (error) => {
      const known =
        isApiError(error) && error.code !== undefined ? SAVE_REFUSALS[error.code] : undefined;
      if (known !== undefined) {
        setRefusal([known]);
        return;
      }
      const fields = readFieldErrors(error);
      if (fields !== null) {
        setRefusal(
          Object.entries(fields).map(([path, message]) =>
            path === "category_code"
              ? `Category: ${message}`
              : `${path.replace(/^calculation\./, "")}: ${message}`,
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
              ? "Only categories that apply on every crop block."
              : "Complete the design to choose a category."}
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          aria-label="Save the subsidy"
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
            <FieldLabel id="quote-category-label">Category</FieldLabel>
            <RadioGroup<string>
              aria-labelledby="quote-category-label"
              aria-describedby={categoryError === null ? undefined : "quote-category-error"}
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
                    {formatInr(option.subsidy, { paise: true })} subsidy · farmer pays{" "}
                    {formatInr(option.farmerShare, { paise: true })}
                  </span>
                </label>
              ))}
            </RadioGroup>
            {ready && options.length === 0 ? (
              <FieldDescription>
                No category applies on every crop block. Change the design.
              </FieldDescription>
            ) : null}
            <FieldError id="quote-category-error">{categoryError}</FieldError>
          </Field>
          {refusal === null ? null : (
            <div
              role="alert"
              className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
            >
              <p className="font-medium text-danger">The subsidy wasn&apos;t saved</p>
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
            loadingLabel="Saving…"
            successLabel="Saved"
            errorLabel="Not saved"
          >
            Save the subsidy
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
