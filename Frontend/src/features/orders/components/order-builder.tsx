"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { AlertCircleIcon, ArrowLeft01Icon } from "@hugeicons/core-free-icons";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

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
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { useCreateOrder, useSaveOrderDraft } from "@/features/orders/api/orders.mutations";
import {
  ORDER_TYPES,
  ORDERABLE_TYPES,
  PAYMENT_TERMS,
  type Order,
  type OrderLine,
  type OrderPartyRequest,
  type StaffOrderType,
} from "@/features/orders/api/orders.schemas";
import {
  ORDER_TYPE_LABELS,
  PAYMENT_TERMS_LABELS,
  orderNumber,
} from "@/features/orders/lib/order-labels";
import { orderRefusal } from "@/features/orders/lib/order-lifecycle";
import { quotationKeys } from "@/features/quotations/api/quotations.queries";
import {
  EXPORT_COUNTRY_MAX_LENGTH,
  type TaxTreatment,
} from "@/features/quotations/api/quotations.schemas";
import {
  PricedItemsCard,
  PricedSummary,
  pricingStatus,
  saveBlocker,
  TextField,
} from "@/features/quotations/components/builder-parts";
import { emptyLine, usePricedLines } from "@/features/quotations/hooks/use-priced-lines";
import {
  linesToSave,
  readAnyFields,
  routeSaveErrors,
  type DraftLine,
  type PricingContext,
} from "@/features/quotations/lib/builder-lines";
import { TAX_TREATMENT_LABELS } from "@/features/quotations/lib/quotation-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { useExportSampleSettings } from "@/features/settings/hooks/use-export-sample-settings";
import { LineAvailability, OrderToField } from "@/features/stock/components/order-stock";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createRequestId } from "@/lib/api/request-id";
import { formatInr, normalizeIndianMobile } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import {
  SubsidyFields,
  subsidyDraftProblems,
  subsidyFieldErrors,
  subsidyRequest,
  type SubsidyDraft,
  type SubsidyProblems,
} from "./order-subsidy-fields";

const log = createLogger({
  file: "features/orders/components/order-builder.tsx",
  dataId: "SO-005",
});

/** What the builder starts from: a lead (or nothing) for a new order, or a draft to edit. */
export type OrderBuilderSource =
  | { readonly mode: "create"; readonly lead: Lead | null }
  | { readonly mode: "edit"; readonly order: Order };

const OrderTypeSchema = z.enum(ORDER_TYPES);

type OrderableType = (typeof ORDERABLE_TYPES)[number];

function orderableType(value: string): value is OrderableType {
  return ORDERABLE_TYPES.some((type) => type === value);
}

/** SO-008, SO-010 · What the builder may make: Subsidised, Export and Sample too, for staff. */
type BuildableType = StaffOrderType;

const STAFF_ONLY_TYPES = [
  "subsidised",
  "export",
  "sample",
] as const satisfies readonly StaffOrderType[];

function buildableType(value: string): value is BuildableType {
  return orderableType(value) || STAFF_ONLY_TYPES.some((type) => type === value);
}

const orderHeaderSchema = z.object({
  orderType: OrderTypeSchema,
  /** SO-010 · Checked against the type when saving: an export needs it. */
  exportCountry: z
    .string()
    .trim()
    .max(EXPORT_COUNTRY_MAX_LENGTH, "Keep the country under 100 characters"),
  partyName: z.string().trim().min(1, "Enter who the order is for").max(200),
  partyMobile: z
    .string()
    .trim()
    .refine((value) => value === "" || normalizeIndianMobile(value) !== null, {
      message: "Enter a 10-digit Indian mobile number, or leave it empty",
    }),
  partyAddress: z.string().trim().max(500, "Keep the address under 500 characters"),
  partyGstin: z
    .string()
    .trim()
    .regex(/^$|^[0-9]{2}[A-Za-z]{5}[0-9]{4}[A-Za-z][0-9A-Za-z]{3}$/, {
      message: "A GSTIN is 15 characters, like 24AAACP1234A1Z5",
    }),
  place: z.custom<TerritoryChoice | null>(
    (value) => value !== null && typeof value === "object",
    "Choose where the goods go",
  ),
  deliveryAddress: z.string().trim().max(500, "Keep the address under 500 characters"),
  paymentTerms: z.enum(PAYMENT_TERMS),
  remarks: z.string().trim().max(2000, "Keep the remarks under 2,000 characters"),
});

type OrderHeaderForm = z.infer<typeof orderHeaderSchema>;

const HEADER_FIELD_NAMES: readonly (keyof OrderHeaderForm)[] = [
  "orderType",
  "exportCountry",
  "partyName",
  "partyMobile",
  "partyAddress",
  "partyGstin",
  "place",
  "deliveryAddress",
  "remarks",
];

function headerDefaults(source: OrderBuilderSource): OrderHeaderForm {
  if (source.mode === "create") {
    const { lead } = source;
    return {
      orderType: lead?.type === "industrial" ? "industrial" : "commercial",
      exportCountry: "",
      partyName: lead?.customerName ?? "",
      partyMobile: lead?.phone ?? "",
      partyAddress:
        lead === null ? "" : [lead.village, lead.territory.name].filter(Boolean).join(", "),
      partyGstin: "",
      place: lead === null ? null : lead.territory,
      deliveryAddress: "",
      paymentTerms: "full_payment",
      remarks: "",
    };
  }
  const { order } = source;
  return {
    // SO-008 · A subsidised draft (and any type the builder doesn't offer) keeps its type
    orderType: order.orderType,
    exportCountry: order.exportCountry ?? "",
    partyName: order.party.name,
    partyMobile: order.party.mobile ?? "",
    partyAddress: order.party.address ?? "",
    partyGstin: order.party.gstin ?? "",
    place: order.placeOfSupply,
    deliveryAddress: order.deliveryAddress ?? "",
    paymentTerms: order.paymentTerms,
    remarks: order.remarks ?? "",
  };
}

function partyFrom(values: OrderHeaderForm): OrderPartyRequest {
  const mobile = values.partyMobile.trim();
  return {
    name: values.partyName.trim(),
    mobile: mobile === "" ? null : (normalizeIndianMobile(mobile) ?? mobile),
    address: values.partyAddress.trim() === "" ? null : values.partyAddress.trim(),
    // SO-010 · An export buyer has no GSTIN (422 export_party_gstin).
    gstin:
      values.orderType === "export" || values.partyGstin.trim() === ""
        ? null
        : values.partyGstin.trim().toUpperCase(),
  };
}

function orNull(value: string): string | null {
  return value.trim() === "" ? null : value.trim();
}

/** "18.000" → "18", "2.500" → "2.5". */
function trimZeros(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

/** A saved order's lines, back as rows to edit. */
function draftLinesFromOrder(lines: readonly OrderLine[]): DraftLine[] {
  return lines.map((line) => ({
    key: createRequestId(),
    product: {
      id: line.productId,
      code: null,
      description: line.description,
      uom: line.uom,
      uomDecimals: line.uomDecimals,
      hsnCode: line.hsnCode,
      gstSlab: line.gstSlab,
      packMultiple: null,
    },
    qty: trimZeros(line.qty),
    discounts: [
      trimZeros(line.discounts[0].pct),
      trimZeros(line.discounts[1].pct),
      trimZeros(line.discounts[2].pct),
    ],
  }));
}

/** SO-010 · What the sample setting makes of a sample order, in words. */
export function sampleHint(pricing: "free" | "charged", maxValue: number | null): string {
  const limit =
    maxValue === null ? "" : ` It may be worth up to ${formatInr(String(maxValue))} at list price.`;
  return pricing === "free"
    ? `Staff only. A free sample: every line is 100 % off and the total is ₹0; the approval runs on the list value.${limit}`
    : `Staff only. Priced like a commercial order.${limit}`;
}

/**
 * SO-005 · An order typed in line by line, without a quotation: from a qualified lead, or
 * afresh with the party and where the goods go; or a draft's items and header edited. Every
 * figure is priced by the backend as the lines change. Saving sends what the preview priced;
 * if a price moved since, the backend answers `rate_changed` and the builder prices again.
 * An order made from quotations keeps the party they fixed.
 */
export function OrderBuilder({ source }: { source: OrderBuilderSource }): React.JSX.Element {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [initialHeader] = useState(() => headerDefaults(source));
  const form = useForm<OrderHeaderForm>({
    resolver: zodResolver(orderHeaderSchema),
    defaultValues: initialHeader,
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const place = useWatch({ control: form.control, name: "place" });
  const fromQuotations = source.mode === "edit" && source.order.quotations.length > 0;
  // SO-007: an amended order keeps its type (422 order_type_fixed). FS-042 rule 18: so does a
  // draft from quotations, or one the builder can't make.
  const amended = source.mode === "edit" && source.order.amendCount > 0;
  const typeFixed =
    source.mode === "edit" && (amended || fromQuotations || !orderableType(source.order.orderType));
  // The place is fixed by the lead, or by the draft once saved.
  const placeFixed = source.mode === "edit" || source.lead !== null;
  const staff = useIsStaff();
  const canSeeStock = useCan("stock", "view");
  // DISP-003 · Staff pick "Order to" and see stock; a dealer's order comes from the default.
  const showsStock = staff && canSeeStock;
  const initialWarehouse = source.mode === "edit" ? (source.order.warehouse?.id ?? null) : null;
  const [warehouseId, setWarehouseId] = useState<string | null>(initialWarehouse);
  const typeChoices: readonly BuildableType[] =
    source.mode === "create" && staff ? [...ORDERABLE_TYPES, ...STAFF_ONLY_TYPES] : ORDERABLE_TYPES;
  // SO-008 · A subsidised order typed in names its leads and subsidy; the lead it starts from
  // is the first (FS-054 rule 6)
  const [subsidyDraft, setSubsidyDraft] = useState<SubsidyDraft>(() => ({
    leads:
      source.mode === "create" && source.lead !== null
        ? [{ id: source.lead.id, code: source.lead.code, name: source.lead.customerName }]
        : [],
    material: "",
    amount: "",
    payable: "",
  }));
  const [subsidyShown, setSubsidyShown] = useState(false);
  const [subsidyServer, setSubsidyServer] = useState<SubsidyProblems>({});

  const partnerId =
    source.mode === "create"
      ? (source.lead?.channelPartner?.id ?? null)
      : (source.order.partner?.id ?? null);
  const asOf = source.mode === "edit" ? source.order.priceEffectiveDate : null;
  const placeId = place?.id ?? "";
  // MSTR-008 · The order's type picks its sale type's price list first, as the save will.
  const orderType = useWatch({ control: form.control, name: "orderType" });
  // SO-010 · An export is priced with the tax it will store: its own once made, else the
  // setting. A sample shows what the setting makes of it.
  const exportOrSample = orderType === "export" || orderType === "sample";
  const exportSample = useExportSampleSettings(source.mode === "create" && exportOrSample);
  const taxTreatment: TaxTreatment =
    orderType !== "export"
      ? "domestic"
      : source.mode === "edit"
        ? source.order.taxTreatment
        : exportSample.exportTreatment;
  const context = useMemo<PricingContext>(
    () => ({
      placeOfSupplyTerritoryId: placeId,
      partnerId,
      asOf,
      salesType: orderType,
      taxTreatment,
    }),
    [placeId, partnerId, asOf, orderType, taxTreatment],
  );
  const priced = usePricedLines(context, () =>
    source.mode === "edit" && source.order.lines.length > 0
      ? draftLinesFromOrder(source.order.lines)
      : [emptyLine()],
  );
  const [formError, setFormError] = useState<{
    title: string;
    description: string;
    reference?: string | undefined;
  } | null>(null);
  const idempotency = useIdempotencyKey();
  const create = useCreateOrder();
  const saveDraft = useSaveOrderDraft();
  const subsidised = source.mode === "create" && orderType === "subsidised";
  const subsidyLocal = subsidised ? subsidyDraftProblems(subsidyDraft) : {};
  const subsidyProblems: SubsidyProblems = {
    ...(subsidyShown ? subsidyLocal : {}),
    ...subsidyServer,
  };

  const save = useAsyncAction({
    action: async (values: OrderHeaderForm) => {
      const lines =
        priced.plan.request !== null && priced.snapshot !== null
          ? linesToSave(priced.plan, priced.snapshot.preview)
          : [];
      const common = {
        delivery_address: orNull(values.deliveryAddress),
        payment_terms: values.paymentTerms,
        remarks: orNull(values.remarks),
      };
      if (source.mode === "create") {
        const type = buildableType(values.orderType) ? values.orderType : "commercial";
        const body = {
          order_type: type,
          ...(type === "export" ? { export_country: values.exportCountry.trim() } : {}),
          // a subsidised order takes its leads from the subsidy (422 lead_from_subsidy)
          ...(type === "subsidised"
            ? { subsidy: subsidyRequest(subsidyDraft) }
            : source.lead === null
              ? {}
              : { lead_id: source.lead.id }),
          ...(partnerId === null ? {} : { partner_id: partnerId }),
          party: partyFrom(values),
          place_of_supply_territory_id: values.place?.id ?? "",
          ...common,
          lines,
          ...(showsStock && warehouseId !== null ? { warehouse_id: warehouseId } : {}),
        };
        return create.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
      }
      const warehouseChanged = showsStock && warehouseId !== initialWarehouse;
      const headerChanged =
        warehouseChanged || JSON.stringify(values) !== JSON.stringify(initialHeader);
      // Only a changed type is sent: an order from quotations, or a subsidised one, keeps its
      // own (422 order_type_fixed)
      const newType =
        values.orderType !== initialHeader.orderType && orderableType(values.orderType)
          ? { order_type: values.orderType }
          : {};
      const countryChanged =
        values.orderType === "export" &&
        values.exportCountry.trim() !== initialHeader.exportCountry;
      const headerBody = {
        ...newType,
        ...(countryChanged ? { export_country: values.exportCountry.trim() } : {}),
        ...(fromQuotations ? {} : { party: partyFrom(values) }),
        ...common,
        ...(warehouseChanged ? { warehouse_id: warehouseId } : {}),
        expected_status: "draft" as const,
      };
      const linesBody = { lines, expected_status: "draft" as const };
      return saveDraft.mutateAsync({
        orderId: source.order.id,
        header: headerChanged
          ? { body: headerBody, idempotencyKey: idempotency.keyFor(headerBody) }
          : null,
        lines: {
          body: linesBody,
          idempotencyKey: idempotency.keyFor({ id: source.order.id, ...linesBody }),
        },
      });
    },
    logger: log,
    fn: source.mode === "create" ? "handleCreateDirectOrder" : "handleSaveOrderDraft",
    dataId: "SO-005",
    onSuccess: (order) => {
      idempotency.reset();
      toast.success(source.mode === "create" ? "Order saved as a draft" : "Draft updated", {
        description: `${order.party.name} · submit it for approval when ready.`,
      });
      router.push(`/sales-orders/${order.id}`);
    },
    onError: (error) => {
      handleSaveError(error);
    },
  });

  function handleSaveError(error: unknown): void {
    const fields = isApiError(error) && error.details !== undefined ? readAnyFields(error) : {};
    setSubsidyServer(subsidised ? subsidyFieldErrors(error) : {});
    const routed = routeSaveErrors(fields, priced.plan.keys);
    priced.setLineErrors(routed.lines);
    for (const [field, message] of Object.entries(routed.header)) {
      const name = HEADER_FIELD_NAMES.find((candidate) => candidate === field);
      if (name !== undefined) form.setError(name, { type: "server", message });
    }
    if (!isApiError(error)) {
      const view = toUserFacingError(error);
      setFormError({ title: view.title, description: view.description });
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
      case "lead_not_open":
        setFormError({
          title: "This lead can't take an order",
          description:
            "Only a qualified lead, or one further on, takes an order. Qualify it first.",
        });
        return;
      case "order_type_unsupported":
        setFormError({ title: "That order type isn't built yet", description: error.message });
        return;
      case "order_type_fixed":
        setFormError({
          title: "The order type can't change now",
          description: "This order was amended after approval, so it keeps its type.",
        });
        return;
      // SO-010 · the export's and the sample's refusals
      case "export_country_required":
        form.setError("exportCountry", { type: "server", message: "Enter the buyer's country." });
        setFormError(null);
        return;
      case "export_party_gstin":
        setFormError({
          title: "An export buyer has no GSTIN",
          description: "Leave the GSTIN empty for an export.",
        });
        return;
      case "lut_missing":
        setFormError({
          title: "No LUT covers this date",
          description:
            "Ask an admin to record this year's LUT in Products & prices → Seller GSTINs.",
        });
        return;
      case "sample_over_limit":
        setFormError({
          title: "This sample is worth too much",
          description:
            exportSample.sampleMaxValue === null
              ? error.message
              : `A sample may be worth up to ${formatInr(String(exportSample.sampleMaxValue))} at list price. Take some items off.`,
        });
        return;
      case "sample_from_quotation":
      case "type_mismatch":
      case "export_country_not_export":
        setFormError({ title: "That order type doesn't fit", description: error.message });
        return;
      // SO-008 · the subsidised order's refusals, in the order's words
      case "subsidy_above_material":
      case "payable_above_material":
      case "lead_not_visible":
      case "subsidy_missing":
      case "lead_from_subsidy":
      case "type_staff_only": {
        const refusal = orderRefusal(error);
        setFormError({ title: refusal.title, description: refusal.message });
        return;
      }
      case "status_changed":
      case "order_not_draft":
        setFormError({
          title: "This order has moved on",
          description:
            "Someone submitted or changed it while you were editing. Open it to see where it stands.",
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

  const blocker =
    place === null
      ? "Choose where the goods go first."
      : priced.rowsReady === 0
        ? "Add at least one item."
        : subsidised && subsidyDraft.leads.length === 0
          ? "Add the farmer's lead for the subsidy."
          : saveBlocker(priced);
  const canSave = blocker === null && priced.upToDate && !save.isBusy;

  const title = source.mode === "create" ? "New order" : `Edit ${orderNumber(source.order)}`;
  const backHref: `/leads/${string}` | `/sales-orders/${string}` | "/sales-orders" =
    source.mode === "edit"
      ? `/sales-orders/${source.order.id}`
      : source.lead === null
        ? "/sales-orders"
        : `/leads/${source.lead.id}`;
  const leadCode =
    source.mode === "create" ? (source.lead?.code ?? null) : (source.order.lead?.code ?? null);

  return (
    <form
      noValidate
      aria-label={title}
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        setFormError(null);
        setSubsidyShown(true);
        setSubsidyServer({});
        void form.handleSubmit((values) => {
          if (subsidised && Object.keys(subsidyLocal).length > 0) return;
          if (values.orderType === "export" && values.exportCountry.trim() === "") {
            form.setError("exportCountry", {
              type: "required",
              message: "Enter the buyer's country.",
            });
            return;
          }
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
          {source.mode === "edit"
            ? "Back to the order"
            : source.lead === null
              ? "All orders"
              : "Back to the lead"}
        </Link>
        <h2 className="text-xl font-semibold text-foreground">{title}</h2>
        <p className="text-sm text-muted-foreground">
          {initialHeader.partyName === ""
            ? "Typed in without a quotation"
            : initialHeader.partyName}
          {leadCode === null ? null : (
            <>
              {" "}
              · <span className="font-mono">{leadCode}</span>
            </>
          )}{" "}
          · Saved as a draft; it is numbered when submitted for approval.
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
          <PricedItemsCard priced={priced} importInto="order" />

          <Card>
            <CardHeader>
              <div className="flex flex-col gap-0.5">
                <CardTitle level={3}>Party and delivery</CardTitle>
                <CardDescription>
                  {fromQuotations
                    ? "The quotations fixed the party; delivery and terms can change."
                    : "Printed on the order and its PDF."}
                </CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <FieldGroup className="grid gap-4 sm:grid-cols-2">
                {typeFixed ? (
                  <Field className="sm:col-span-2">
                    <FieldLabel>Order type</FieldLabel>
                    <p className="text-sm text-foreground">{ORDER_TYPE_LABELS[orderType]}</p>
                    <FieldDescription>
                      {amended
                        ? "Fixed: the order was amended after approval, so it keeps its type."
                        : fromQuotations
                          ? "An order made from quotations keeps its type."
                          : "This order keeps its type."}
                    </FieldDescription>
                  </Field>
                ) : (
                  <Controller
                    control={form.control}
                    name="orderType"
                    render={({ field }) => (
                      <Field className="sm:col-span-2">
                        <FieldLabel id="order-type-label">Order type</FieldLabel>
                        <RadioGroup<BuildableType>
                          aria-labelledby="order-type-label"
                          value={buildableType(field.value) ? field.value : "commercial"}
                          onValueChange={field.onChange}
                          className="flex-row flex-wrap gap-5"
                        >
                          {typeChoices.map((type) => (
                            <label
                              key={type}
                              className="flex items-center gap-2 text-sm text-foreground"
                            >
                              <RadioGroupItem value={type} />
                              {ORDER_TYPE_LABELS[type]}
                            </label>
                          ))}
                        </RadioGroup>
                        <FieldDescription>
                          {field.value === "subsidised"
                            ? "Staff only. Name the farmers' leads and the subsidy below."
                            : field.value === "export"
                              ? `Staff only. ${TAX_TREATMENT_LABELS[taxTreatment]}, fixed when the draft is saved.`
                              : field.value === "sample"
                                ? sampleHint(
                                    exportSample.samplePricing,
                                    exportSample.sampleMaxValue,
                                  )
                                : typeChoices.includes("subsidised")
                                  ? "Marketing material and replacements are made elsewhere."
                                  : "Export, sample and subsidised orders are made by staff."}
                        </FieldDescription>
                      </Field>
                    )}
                  />
                )}
                <TextField
                  id="order-party-name"
                  label="Party"
                  error={errors.partyName?.message}
                  className="sm:col-span-2"
                >
                  {(aria) => (
                    <Input
                      autoComplete="name"
                      disabled={fromQuotations}
                      {...aria}
                      {...form.register("partyName")}
                    />
                  )}
                </TextField>
                <TextField
                  id="order-party-mobile"
                  label="Mobile"
                  optional
                  error={errors.partyMobile?.message}
                  description="The order's confirmation goes here on WhatsApp."
                >
                  {(aria) => (
                    <Input
                      type="tel"
                      inputMode="tel"
                      autoComplete="tel"
                      disabled={fromQuotations}
                      {...aria}
                      {...form.register("partyMobile")}
                    />
                  )}
                </TextField>
                {orderType === "export" ? (
                  <TextField
                    id="order-export-country"
                    label="Country"
                    error={errors.exportCountry?.message}
                    description="Where the buyer is. An export buyer has no GSTIN."
                  >
                    {(aria) => (
                      <Input
                        autoComplete="country-name"
                        maxLength={EXPORT_COUNTRY_MAX_LENGTH}
                        {...aria}
                        {...form.register("exportCountry")}
                      />
                    )}
                  </TextField>
                ) : (
                  <TextField
                    id="order-party-gstin"
                    label="GSTIN"
                    optional
                    error={errors.partyGstin?.message}
                  >
                    {(aria) => (
                      <Input
                        autoComplete="off"
                        className="uppercase"
                        disabled={fromQuotations}
                        {...aria}
                        {...form.register("partyGstin")}
                      />
                    )}
                  </TextField>
                )}
                <TextField
                  id="order-party-address"
                  label="Party's address"
                  optional
                  error={errors.partyAddress?.message}
                  className="sm:col-span-2"
                >
                  {(aria) => (
                    <Textarea
                      rows={2}
                      disabled={fromQuotations}
                      {...aria}
                      {...form.register("partyAddress")}
                    />
                  )}
                </TextField>
                <Controller
                  control={form.control}
                  name="place"
                  render={({ field, fieldState }) => (
                    <Field
                      data-invalid={fieldState.error ? true : undefined}
                      className="sm:col-span-2"
                    >
                      <FieldLabel htmlFor="order-place">Where the goods go</FieldLabel>
                      <TerritoryPicker
                        id="order-place"
                        value={field.value}
                        onValueChange={field.onChange}
                        onBlur={field.onBlur}
                        disabled={placeFixed}
                        aria-invalid={fieldState.error ? true : undefined}
                        aria-describedby={
                          fieldState.error ? "order-place-error" : "order-place-hint"
                        }
                      />
                      {fieldState.error ? null : (
                        <FieldDescription id="order-place-hint">
                          {placeFixed
                            ? "The place of supply, from the lead. It sets CGST and SGST, or IGST."
                            : "The place of supply. It sets CGST and SGST, or IGST, and the prices."}
                        </FieldDescription>
                      )}
                      <FieldError id="order-place-error">{fieldState.error?.message}</FieldError>
                    </Field>
                  )}
                />
                <TextField
                  id="order-delivery"
                  label="Delivery address"
                  optional
                  error={errors.deliveryAddress?.message}
                  className="sm:col-span-2"
                  description="When it differs from the party's address."
                >
                  {(aria) => <Textarea rows={2} {...aria} {...form.register("deliveryAddress")} />}
                </TextField>
                {showsStock ? (
                  <OrderToField
                    value={warehouseId}
                    onValueChange={setWarehouseId}
                    className="sm:col-span-2"
                  />
                ) : null}
                <Controller
                  control={form.control}
                  name="paymentTerms"
                  render={({ field }) => (
                    <Field className="sm:col-span-2">
                      <FieldLabel id="order-terms-label">Payment</FieldLabel>
                      <RadioGroup<(typeof PAYMENT_TERMS)[number]>
                        aria-labelledby="order-terms-label"
                        value={field.value}
                        onValueChange={field.onChange}
                        className="flex-row flex-wrap gap-5"
                      >
                        {PAYMENT_TERMS.map((terms) => (
                          <label
                            key={terms}
                            className="flex items-center gap-2 text-sm text-foreground"
                          >
                            <RadioGroupItem value={terms} />
                            {PAYMENT_TERMS_LABELS[terms]}
                          </label>
                        ))}
                      </RadioGroup>
                      <FieldDescription>
                        Recorded on the order; there is no credit check.
                      </FieldDescription>
                    </Field>
                  )}
                />
                <TextField
                  id="order-remarks"
                  label="Remarks"
                  optional
                  error={errors.remarks?.message}
                  className="sm:col-span-2"
                >
                  {(aria) => <Textarea rows={2} {...aria} {...form.register("remarks")} />}
                </TextField>
              </FieldGroup>
            </CardContent>
          </Card>

          {subsidised ? (
            <Card>
              <CardHeader>
                <div className="flex flex-col gap-0.5">
                  <CardTitle level={3}>Subsidy</CardTitle>
                  <CardDescription>
                    The leads it covers, what the scheme pays, and what the farmer pays.
                  </CardDescription>
                </div>
              </CardHeader>
              <CardContent>
                <SubsidyFields
                  idPrefix="new-order-subsidy"
                  draft={subsidyDraft}
                  onDraftChange={(next) => {
                    setSubsidyDraft(next);
                    setSubsidyServer({});
                  }}
                  problems={subsidyProblems}
                  total={priced.totals?.total ?? null}
                />
              </CardContent>
            </Card>
          ) : null}
        </div>

        <Card className="lg:sticky lg:top-4">
          <CardHeader>
            <div className="flex flex-col gap-0.5">
              <CardTitle level={3}>Summary</CardTitle>
              <CardDescription aria-live="polite">
                {place === null
                  ? "Choose where the goods go to see prices."
                  : pricingStatus(priced)}
              </CardDescription>
            </div>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <PricedSummary priced={priced} />
            {showsStock ? (
              <LineAvailability
                warehouseId={warehouseId}
                lines={priced.lines.flatMap((line) =>
                  line.product === null || line.qty.trim() === ""
                    ? []
                    : [
                        {
                          key: line.key,
                          productId: line.product.id,
                          name: line.product.description,
                          qty: line.qty.trim(),
                          uom: line.product.uom,
                        },
                      ],
                )}
              />
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
                {source.mode === "create" ? "Save draft order" : "Save changes"}
              </Button>
              {blocker === null ? null : <p className="text-xs text-muted-foreground">{blocker}</p>}
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
