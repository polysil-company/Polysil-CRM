"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon, AlertCircleIcon, ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState } from "react-hook-form";
import { toast } from "sonner";

import { ErrorReference } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { useCreateQuotation, useUpdateDraft } from "@/features/quotations/api/quotations.mutations";
import {
  quotationKeys,
  quotePreviewQueryOptions,
} from "@/features/quotations/api/quotations.queries";
import {
  PRICED_SALES_TYPES,
  quotationHeaderFormSchema,
  type PartyRequest,
  type Quotation,
  type QuotationHeaderForm,
  type QuotePreview,
  type QuoteLinesRequest,
} from "@/features/quotations/api/quotations.schemas";
import {
  draftLinesFrom,
  isPriceable,
  lineIssue,
  linesToSave,
  pricedByKey,
  previewRequestFor,
  routeSaveErrors,
  type DraftLine,
  type PricingContext,
} from "@/features/quotations/lib/builder-lines";
import {
  SALES_TYPE_LABELS,
  formatRate,
  parseWarnings,
  quotationTitle,
} from "@/features/quotations/lib/quotation-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { formatInr, normalizeIndianMobile } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import { QuotationLineRow } from "./quotation-line-row";

const log = createLogger({
  file: "features/quotations/components/quotation-builder.tsx",
  dataId: "QUOT-004",
});

/** Price once typing pauses for this long. */
const PREVIEW_DEBOUNCE_MS = 400;

/** What the builder starts from: a lead for a new draft, or a draft to edit. */
export type BuilderSource =
  | { readonly mode: "create"; readonly lead: Lead }
  | { readonly mode: "edit"; readonly quotation: Quotation };

/** The header fields a refusal can name. */
const HEADER_FIELD_NAMES: readonly (keyof QuotationHeaderForm)[] = [
  "salesType",
  "partyName",
  "partyMobile",
  "partyAddress",
  "partyGstin",
  "terms",
];

/** A preview request that never goes out: the query is off while there is nothing to price. */
const NOTHING_TO_PRICE: QuoteLinesRequest = { place_of_supply_territory_id: "", lines: [] };

function emptyLine(): DraftLine {
  return { key: createRequestId(), product: null, qty: "", discounts: ["", "", ""] };
}

function contextFor(source: BuilderSource): PricingContext {
  return source.mode === "create"
    ? {
        placeOfSupplyTerritoryId: source.lead.territory.id,
        partnerId: source.lead.channelPartner?.id ?? null,
        asOf: null,
      }
    : {
        placeOfSupplyTerritoryId: source.quotation.placeOfSupply.territory.id,
        partnerId: source.quotation.partner?.id ?? null,
        asOf: source.quotation.priceEffectiveDate,
      };
}

function headerDefaults(source: BuilderSource): QuotationHeaderForm {
  if (source.mode === "create") {
    const { lead } = source;
    return {
      salesType: lead.type === "industrial" ? "industrial" : "commercial",
      partyName: lead.customerName,
      partyMobile: lead.phone,
      partyAddress: [lead.village, lead.territory.name].filter(Boolean).join(", "),
      partyGstin: "",
      terms: "",
    };
  }
  const { quotation } = source;
  return {
    salesType: quotation.salesType === "industrial" ? "industrial" : "commercial",
    partyName: quotation.party.name,
    partyMobile: quotation.party.mobile,
    partyAddress: quotation.party.address ?? "",
    partyGstin: quotation.party.gstin ?? "",
    terms: quotation.terms ?? "",
  };
}

function partyFrom(values: QuotationHeaderForm): PartyRequest {
  return {
    name: values.partyName.trim(),
    mobile: normalizeIndianMobile(values.partyMobile) ?? values.partyMobile.trim(),
    address: values.partyAddress.trim() === "" ? null : values.partyAddress.trim(),
    gstin: values.partyGstin.trim() === "" ? null : values.partyGstin.trim().toUpperCase(),
  };
}

/** The last preview that belongs to a plan, so rows keep their figures while the next loads. */
interface PricedSnapshot {
  readonly keys: readonly string[];
  readonly preview: QuotePreview;
}

/**
 * QUOT-004, QUOT-005 · Build a draft quotation: who it is for, its items, and — as the lines
 * change — every figure priced by the backend (`POST /pricing/quote-lines`), which the screen
 * prints and never computes. Saving sends what the preview priced; if a price or tax rate
 * moved since, the backend answers `rate_changed`, the builder names the lines, prices them
 * again and the user saves again.
 */
export function QuotationBuilder({ source }: { source: BuilderSource }): React.JSX.Element {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [context] = useState(() => contextFor(source));
  const [lines, setLines] = useState<DraftLine[]>(() =>
    source.mode === "edit" && source.quotation.lines.length > 0
      ? draftLinesFrom(source.quotation.lines, createRequestId)
      : [emptyLine()],
  );
  const [lineErrors, setLineErrors] = useState<Readonly<Record<string, string>>>({});
  const [formError, setFormError] = useState<{
    title: string;
    description: string;
    reference?: string | undefined;
  } | null>(null);
  const [initialHeader] = useState(() => headerDefaults(source));
  const form = useForm<QuotationHeaderForm>({
    resolver: zodResolver(quotationHeaderFormSchema),
    defaultValues: initialHeader,
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const idempotency = useIdempotencyKey();
  const create = useCreateQuotation();
  const update = useUpdateDraft();

  // ── pricing ──────────────────────────────────────────────────────────────
  const plan = useMemo(() => previewRequestFor(lines, context), [lines, context]);
  const debouncedPlan = useDebouncedValue(plan, PREVIEW_DEBOUNCE_MS);
  const preview = useQuery({
    ...quotePreviewQueryOptions(debouncedPlan.request ?? NOTHING_TO_PRICE),
    enabled: debouncedPlan.request !== null,
  });

  const [snapshot, setSnapshot] = useState<PricedSnapshot | null>(null);
  if (
    preview.data !== undefined &&
    !preview.isPlaceholderData &&
    snapshot?.preview !== preview.data
  ) {
    setSnapshot({ keys: debouncedPlan.keys, preview: preview.data });
  }
  const upToDate =
    plan.request === null ||
    (debouncedPlan === plan &&
      preview.data !== undefined &&
      !preview.isPlaceholderData &&
      !preview.isFetching);
  const pricing = plan.request !== null && !upToDate && !preview.isError;
  const priced = pricedByKey(snapshot?.preview, snapshot?.keys ?? []);
  const totals = plan.request === null ? null : (snapshot?.preview.totals ?? null);
  const previewErrors =
    preview.isError && debouncedPlan === plan
      ? routeSaveErrors(readFieldErrors(preview.error) ?? {}, debouncedPlan.keys).lines
      : {};
  const previewFailed =
    preview.isError && debouncedPlan === plan && Object.keys(previewErrors).length === 0;

  const rowsWithIssues = lines.filter((line) => lineIssue(line) !== null).length;
  const rowsReady = lines.filter(isPriceable).length;

  // ── lines ────────────────────────────────────────────────────────────────
  const changeLine = (next: DraftLine): void => {
    setLines((current) => current.map((line) => (line.key === next.key ? next : line)));
    setLineErrors(({ [next.key]: _cleared, ...rest }) => rest);
  };
  const removeLine = (key: string): void => {
    setLines((current) =>
      current.length === 1 ? [emptyLine()] : current.filter((line) => line.key !== key),
    );
  };
  const addLine = (): void => {
    setLines((current) => [...current, emptyLine()]);
  };

  // ── saving ───────────────────────────────────────────────────────────────
  const save = useAsyncAction({
    action: async (values: QuotationHeaderForm) => {
      const saved =
        plan.request !== null && snapshot !== null ? linesToSave(plan, snapshot.preview) : [];
      const party = partyFrom(values);
      const terms = values.terms.trim() === "" ? null : values.terms.trim();
      if (source.mode === "create") {
        const body = {
          lead_id: source.lead.id,
          sales_type: values.salesType,
          party,
          terms,
          lines: saved,
        };
        return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
      }
      const headerChanged = JSON.stringify(values) !== JSON.stringify(initialHeader);
      const headerBody = {
        sales_type: values.salesType,
        party,
        terms,
        expected_status: "draft" as const,
      };
      const linesBody = { lines: saved, expected_status: "draft" as const };
      return update.mutateAsync({
        quotationId: source.quotation.id,
        header: headerChanged
          ? { body: headerBody, idempotencyKey: idempotency.keyFor(headerBody) }
          : null,
        lines: {
          body: linesBody,
          idempotencyKey: idempotency.keyFor({ id: source.quotation.id, ...linesBody }),
        },
      });
    },
    logger: log,
    fn: source.mode === "create" ? "handleCreateDraft" : "handleSaveDraft",
    dataId: "QUOT-004",
    onSuccess: (quotation) => {
      idempotency.reset();
      toast.success(source.mode === "create" ? "Draft saved" : "Draft updated", {
        description: `${quotation.party.name} · ${quotationTitle(quotation)}`,
      });
      router.push(`/quotations/${quotation.id}`);
    },
    onError: (error) => {
      handleSaveError(error);
    },
  });

  function handleSaveError(error: unknown): void {
    const fields = isApiError(error) && error.details !== undefined ? readAnyFields(error) : {};
    const routed = routeSaveErrors(fields, plan.keys);
    setLineErrors(routed.lines);
    for (const [field, message] of Object.entries(routed.header)) {
      const name = HEADER_FIELD_NAMES.find((candidate) => candidate === field);
      if (name !== undefined) {
        form.setError(name, { type: "server", message });
      }
    }
    if (!isApiError(error)) {
      setFormError({
        title: toUserFacingError(error).title,
        description: toUserFacingError(error).description,
      });
      return;
    }
    switch (error.code) {
      case "rate_changed":
        // New figures, so the next save is a new request with a new key.
        idempotency.reset();
        void queryClient.invalidateQueries({ queryKey: quotationKeys.previews() });
        setFormError({
          title: "Prices changed since you priced this",
          description:
            "The items marked below now carry the new figures. Check them, then save again.",
        });
        return;
      case "lead_not_qualified":
        setFormError({
          title: "This lead can't be quoted yet",
          description: "Qualify the lead first, then make its quotation.",
        });
        return;
      case "lead_not_open":
        setFormError({
          title: "This lead is closed",
          description: "Reopen the lead to quote it again.",
        });
        return;
      case "sales_type_unsupported":
        setFormError({ title: "That sales type isn't priced yet", description: error.message });
        return;
      case "status_changed":
      case "quotation_not_draft":
        setFormError({
          title: "This quotation has moved on",
          description:
            "Someone sent or changed it while you were editing. Open it to see where it stands.",
        });
        return;
      default:
        if (Object.keys(routed.header).length > 0 || Object.keys(routed.lines).length > 0) {
          setFormError(null);
          return;
        }
        {
          const view = toUserFacingError(error);
          setFormError({
            title: view.title,
            description: view.description,
            reference: view.reference,
          });
        }
    }
  }

  const canSave =
    rowsWithIssues === 0 &&
    upToDate &&
    !save.isBusy &&
    !previewFailed &&
    Object.keys(previewErrors).length === 0;
  const saveHint =
    rowsWithIssues > 0
      ? `Finish ${rowsWithIssues === 1 ? "one item" : `${String(rowsWithIssues)} items`} first.`
      : pricing
        ? "Pricing…"
        : previewFailed || Object.keys(previewErrors).length > 0
          ? "Fix the pricing first."
          : null;

  const title =
    source.mode === "create" ? "New quotation" : `Edit ${quotationTitle(source.quotation)}`;
  const backHref: `/leads/${string}` | `/quotations/${string}` =
    source.mode === "create" ? `/leads/${source.lead.id}` : `/quotations/${source.quotation.id}`;
  const leadCode =
    source.mode === "create" ? source.lead.code : (source.quotation.lead?.code ?? null);

  return (
    <form
      noValidate
      aria-label={title}
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        setFormError(null);
        void form.handleSubmit((values) => {
          void save.run(values);
        })(event);
      }}
    >
      <div className="flex min-w-0 flex-col gap-1.5">
        <Link
          href={backHref}
          transitionTypes={["nav-back"]}
          className="-ml-1 inline-flex w-fit items-center gap-1 rounded-sm px-1 text-sm text-muted-foreground focus-ring-inset transition-colors duration-fast hover:text-foreground"
        >
          <Icon icon={ArrowLeft01Icon} size="sm" />
          {source.mode === "create" ? "Back to the lead" : "Back to the quotation"}
        </Link>
        <h2 className="text-xl font-semibold text-foreground">{title}</h2>
        <p className="text-sm text-muted-foreground">
          {initialHeader.partyName}
          {leadCode === null ? null : (
            <>
              {" "}
              · <span className="font-mono">{leadCode}</span>
            </>
          )}{" "}
          · Saved as a draft; nothing is sent yet.
        </p>
      </div>

      {formError === null ? null : (
        <div
          role="alert"
          className="flex items-start gap-2.5 rounded-lg border border-border bg-danger-soft p-3 text-sm"
        >
          <Icon icon={AlertCircleIcon} className="mt-0.5 text-danger" />
          <div className="flex min-w-0 flex-col gap-1">
            <p className="font-medium text-danger">{formError.title}</p>
            <p className="text-muted-foreground">{formError.description}</p>
            {formError.reference === undefined ? null : (
              <ErrorReference reference={formError.reference} className="self-start" />
            )}
          </div>
        </div>
      )}

      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-4 lg:col-span-2">
          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <CardTitle level={3}>Items</CardTitle>
                <CardDescription>
                  Each discount is a percentage of what is left after the one before.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <ol aria-label="Items" className="flex flex-col gap-3">
                {lines.map((line, index) => (
                  <QuotationLineRow
                    key={line.key}
                    line={line}
                    index={index}
                    priced={priced.get(line.key)}
                    pricing={pricing}
                    error={lineErrors[line.key] ?? previewErrors[line.key]}
                    canRemove={lines.length > 1 || line.product !== null || line.qty !== ""}
                    onChange={changeLine}
                    onRemove={() => {
                      removeLine(line.key);
                    }}
                  />
                ))}
              </ol>
              <Button type="button" variant="outline" className="self-start" onClick={addLine}>
                <Icon icon={Add01Icon} />
                Add item
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <CardTitle level={3}>Customer and terms</CardTitle>
                <CardDescription>
                  Printed on the quotation. The WhatsApp link goes to this mobile.
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <FieldGroup className="grid gap-4 sm:grid-cols-2">
                <Controller
                  control={form.control}
                  name="salesType"
                  render={({ field }) => (
                    <Field className="sm:col-span-2">
                      <FieldLabel id="quote-sales-type-label">Sales type</FieldLabel>
                      <RadioGroup<(typeof PRICED_SALES_TYPES)[number]>
                        aria-labelledby="quote-sales-type-label"
                        value={field.value}
                        onValueChange={field.onChange}
                        className="flex-row flex-wrap gap-5"
                      >
                        {PRICED_SALES_TYPES.map((type) => (
                          <label
                            key={type}
                            className="flex items-center gap-2 text-sm text-foreground"
                          >
                            <RadioGroupItem value={type} />
                            {SALES_TYPE_LABELS[type]}
                          </label>
                        ))}
                      </RadioGroup>
                      <FieldDescription>
                        Subsidised, export, marketing and sample quotations wait on the
                        client&apos;s rules.
                      </FieldDescription>
                    </Field>
                  )}
                />
                <TextField
                  id="quote-party-name"
                  label="Name"
                  error={errors.partyName?.message}
                  className="sm:col-span-2"
                >
                  {(aria) => (
                    <Input autoComplete="name" {...aria} {...form.register("partyName")} />
                  )}
                </TextField>
                <TextField
                  id="quote-party-mobile"
                  label="Mobile"
                  error={errors.partyMobile?.message}
                >
                  {(aria) => (
                    <Input
                      type="tel"
                      inputMode="tel"
                      autoComplete="tel"
                      {...aria}
                      {...form.register("partyMobile")}
                    />
                  )}
                </TextField>
                <TextField
                  id="quote-party-gstin"
                  label="GSTIN"
                  optional
                  error={errors.partyGstin?.message}
                >
                  {(aria) => (
                    <Input
                      autoComplete="off"
                      className="uppercase"
                      {...aria}
                      {...form.register("partyGstin")}
                    />
                  )}
                </TextField>
                <TextField
                  id="quote-party-address"
                  label="Address"
                  optional
                  error={errors.partyAddress?.message}
                  className="sm:col-span-2"
                >
                  {(aria) => <Textarea rows={2} {...aria} {...form.register("partyAddress")} />}
                </TextField>
                <TextField
                  id="quote-terms"
                  label="Terms"
                  optional
                  error={errors.terms?.message}
                  className="sm:col-span-2"
                  description="Printed at the foot: delivery, installation, payment."
                >
                  {(aria) => <Textarea rows={3} {...aria} {...form.register("terms")} />}
                </TextField>
              </FieldGroup>
            </CardContent>
          </Card>
        </div>

        <Card className="lg:sticky lg:top-4">
          <CardHeader>
            <div className="flex flex-col gap-0.5">
              <CardTitle level={3}>Summary</CardTitle>
              <CardDescription aria-live="polite">
                {rowsReady === 0
                  ? "Add an item to see prices."
                  : pricing
                    ? "Pricing…"
                    : "Priced by the price list in force."}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <BuilderTotals
              totals={totals}
              intraState={snapshot?.preview.intraState ?? true}
              stale={pricing}
            />
            {previewFailed ? (
              <div
                role="alert"
                className="flex flex-col gap-2 rounded-md bg-danger-soft p-3 text-sm"
              >
                <p className="font-medium text-danger">{toUserFacingError(preview.error).title}</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="self-start"
                  onClick={() => void preview.refetch()}
                >
                  Price again
                </Button>
              </div>
            ) : null}
            <BuilderWarnings warnings={snapshot?.preview.warnings ?? []} />
            {source.mode === "edit" && source.quotation.discount !== null ? (
              <p className="text-xs text-muted-foreground">
                At the last save the discount was{" "}
                {formatRate(source.quotation.discount.effectivePct)}; your limit is{" "}
                {source.quotation.discount.ownerLimitPct === null
                  ? "none"
                  : formatRate(source.quotation.discount.ownerLimitPct)}
                . Above it, the quotation needs a manager&apos;s approval before it is sent.
              </p>
            ) : null}
            <div className="flex flex-col gap-2 border-t border-border pt-4">
              <Button
                type="submit"
                state={save.state}
                loadingLabel="Saving…"
                successLabel="Saved"
                errorLabel="Not saved"
                disabled={!canSave && save.state === "idle"}
              >
                {source.mode === "create" ? "Save draft" : "Save changes"}
              </Button>
              {saveHint === null ? null : (
                <p className="text-xs text-muted-foreground">{saveHint}</p>
              )}
              <Link
                href={backHref}
                className={cn(buttonVariants({ variant: "ghost" }), "justify-center")}
              >
                Cancel
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </form>
  );
}

/** The backend's `fields` on any refusal, not only a 422 (a 409 rate_changed carries them too). */
function readAnyFields(error: { details: unknown }): Record<string, string> {
  const details = error.details;
  if (typeof details !== "object" || details === null || !("fields" in details)) {
    return {};
  }
  const { fields } = details;
  if (typeof fields !== "object" || fields === null) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(fields).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

interface FieldAria {
  id: string;
  "aria-invalid": true | undefined;
  "aria-describedby": string | undefined;
}

function TextField({
  id,
  label,
  optional = false,
  error,
  description,
  className,
  children,
}: {
  id: string;
  label: string;
  optional?: boolean;
  error: string | undefined;
  description?: string;
  className?: string;
  children: (aria: FieldAria) => React.ReactNode;
}): React.JSX.Element {
  const errorId = `${id}-error`;
  const descriptionId = `${id}-description`;
  return (
    <Field data-invalid={error ? true : undefined} className={className}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-subtle-foreground">(optional)</span> : null}
      </FieldLabel>
      {children({
        id,
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error ? errorId : description ? descriptionId : undefined,
      })}
      {description && !error ? (
        <FieldDescription id={descriptionId}>{description}</FieldDescription>
      ) : null}
      <FieldError id={errorId}>{error}</FieldError>
    </Field>
  );
}

function BuilderTotals({
  totals,
  intraState,
  stale,
}: {
  totals: QuotePreview["totals"] | null;
  intraState: boolean;
  stale: boolean;
}): React.JSX.Element {
  const rows: { label: string; value: string | null; strong?: boolean }[] = [
    { label: "Gross", value: totals?.gross ?? null },
    { label: "Discount", value: totals?.discount ?? null },
    { label: "Taxable value", value: totals?.taxable ?? null },
    ...(intraState
      ? [
          { label: "CGST", value: totals?.cgst ?? null },
          { label: "SGST", value: totals?.sgst ?? null },
        ]
      : [{ label: "IGST", value: totals?.igst ?? null }]),
    { label: "Total", value: totals?.total ?? null, strong: true },
  ];
  return (
    <dl
      aria-label="Totals"
      className={cn(
        "grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm transition-opacity duration-fast",
        stale && "opacity-60",
      )}
    >
      {rows.map((row) => (
        <div
          key={row.label}
          className={cn(
            "col-span-2 grid grid-cols-subgrid",
            row.strong && "border-t border-border pt-2",
          )}
        >
          <dt className={row.strong ? "font-semibold text-foreground" : "text-muted-foreground"}>
            {row.label}
          </dt>
          <dd
            className={cn(
              "text-right tabular-nums",
              row.strong ? "text-base font-semibold" : "text-foreground",
            )}
          >
            {row.value === null
              ? "—"
              : `${row.label === "Discount" && Number(row.value) !== 0 ? "−" : ""}${formatInr(row.value, { paise: true })}`}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function BuilderWarnings({ warnings }: { warnings: readonly string[] }): React.JSX.Element | null {
  const parsed = parseWarnings(warnings);
  if (parsed.length === 0) {
    return null;
  }
  return (
    <ul aria-label="Pricing notes" className="flex flex-col gap-1.5">
      {parsed.map((warning, index) => (
        <li
          key={`${warning.code}-${String(index)}`}
          className="rounded-md bg-warning-soft px-3 py-2 text-xs text-foreground"
        >
          {warning.code === "provisional_pricing" ? "Indicative pricing: " : null}
          {warning.message}
        </li>
      ))}
    </ul>
  );
}
