"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircleIcon, ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState } from "react-hook-form";
import { toast } from "sonner";

import { ErrorReference } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import type { Lead } from "@/features/leads/api/leads.schemas";
import { useCreateQuotation, useUpdateDraft } from "@/features/quotations/api/quotations.mutations";
import { quotationKeys } from "@/features/quotations/api/quotations.queries";
import {
  PRICED_SALES_TYPES,
  quotationHeaderFormSchema,
  type PartyRequest,
  type Quotation,
  type QuotationHeaderForm,
} from "@/features/quotations/api/quotations.schemas";
import { emptyLine, usePricedLines } from "@/features/quotations/hooks/use-priced-lines";
import {
  draftLinesFrom,
  linesToSave,
  readAnyFields,
  routeSaveErrors,
  type PricingContext,
} from "@/features/quotations/lib/builder-lines";
import {
  SALES_TYPE_LABELS,
  formatRate,
  quotationTitle,
} from "@/features/quotations/lib/quotation-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { normalizeIndianMobile } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import {
  PricedItemsCard,
  PricedSummary,
  pricingStatus,
  saveBlocker,
  TextField,
} from "./builder-parts";

const log = createLogger({
  file: "features/quotations/components/quotation-builder.tsx",
  dataId: "QUOT-004",
});

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
  const priced = usePricedLines(context, () =>
    source.mode === "edit" && source.quotation.lines.length > 0
      ? draftLinesFrom(source.quotation.lines, createRequestId)
      : [emptyLine()],
  );
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

  // ── saving ───────────────────────────────────────────────────────────────
  const save = useAsyncAction({
    action: async (values: QuotationHeaderForm) => {
      const saved =
        priced.plan.request !== null && priced.snapshot !== null
          ? linesToSave(priced.plan, priced.snapshot.preview)
          : [];
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
    const routed = routeSaveErrors(fields, priced.plan.keys);
    priced.setLineErrors(routed.lines);
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

  const blocker = saveBlocker(priced);
  const canSave = blocker === null && priced.upToDate && !save.isBusy;
  const saveHint = blocker;

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
          <PricedItemsCard priced={priced} />

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
              <CardDescription aria-live="polite">{pricingStatus(priced)}</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <PricedSummary priced={priced} />
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
            {/* QUOT-007 · The approval is for the figures the approver saw. */}
            {source.mode === "edit" &&
            (source.quotation.approval?.status === "pending" ||
              source.quotation.approval?.status === "approved") ? (
              <p role="note" className="rounded-md bg-warning-soft p-3 text-xs text-foreground">
                {source.quotation.approval.status === "pending"
                  ? "Saving withdraws the discount approval request that is waiting."
                  : "Saving cancels the discount approval: ask again if the discount is still above your limit."}
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
