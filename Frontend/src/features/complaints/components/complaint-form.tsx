"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon, Delete02Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { Controller, useFieldArray, useForm, useFormState, type FieldPath } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ErrorReference } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateComplaint,
  useSaveComplaintDraft,
} from "@/features/complaints/api/complaints.mutations";
import {
  COMPLAINT_LINES_MAX,
  COMPLAINT_SEVERITIES,
  type Complaint,
  type ComplaintSeverity,
  type CreateComplaintRequest,
  type PatchComplaintRequest,
} from "@/features/complaints/api/complaints.schemas";
import { complaintRefusal, SEVERITY_LABELS } from "@/features/complaints/lib/complaint-labels";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import type { ProductPick } from "@/features/quotations/api/quotations.schemas";
import { ProductPicker } from "@/features/quotations/components/product-picker";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { normalizeIndianMobile, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { DealerPicker, type DealerChoice } from "./dealer-picker";

const log = createLogger({
  file: "features/complaints/components/complaint-form.tsx",
  dataId: "CMPL-003",
});

const QTY_PATTERN = /^\d+(\.\d{1,3})?$/;
const SEVERITY_ITEMS = COMPLAINT_SEVERITIES.map((value) => ({
  value,
  label: SEVERITY_LABELS[value],
}));

interface LineForm {
  product: ProductPick | null;
  supplied: string;
  defective: string;
  frequency: string;
  remark: string;
}

export interface ComplaintFormValues {
  typeId: string;
  severity: ComplaintSeverity;
  description: string;
  contactName: string;
  contactMobile: string;
  territory: TerritoryChoice | null;
  dealer: DealerChoice | null;
  dcNo: string;
  supplyDate: string;
  regNo: string;
  pimsNo: string;
  courierDate: string;
  courierDetail: string;
  lines: LineForm[];
}

const notAfterToday = (value: string): boolean => value === "" || value <= todayInIndia();

const formSchema: z.ZodType<ComplaintFormValues, ComplaintFormValues> = z.object({
  typeId: z.string().min(1, "Choose what kind of complaint it is."),
  severity: z.enum(COMPLAINT_SEVERITIES),
  description: z
    .string()
    .trim()
    .min(1, "Say what went wrong.")
    .max(2000, "Keep it under 2000 characters."),
  contactName: z
    .string()
    .trim()
    .min(1, "Whom should we contact?")
    .max(120, "Keep it under 120 characters."),
  contactMobile: z
    .string()
    .refine(
      (value) => normalizeIndianMobile(value) !== null,
      "Enter a 10-digit Indian mobile number.",
    ),
  territory: z.custom<TerritoryChoice | null>(
    (value) => value !== null && typeof value === "object",
    "Choose where the material is installed.",
  ),
  dealer: z.custom<DealerChoice | null>(() => true),
  dcNo: z.string().max(60, "Keep it under 60 characters."),
  supplyDate: z.string().refine(notAfterToday, "It can't be after today."),
  regNo: z.string().max(60, "Keep it under 60 characters."),
  pimsNo: z.string().max(60, "Keep it under 60 characters."),
  courierDate: z.string().refine(notAfterToday, "It can't be after today."),
  courierDetail: z.string().max(200, "Keep it under 200 characters."),
  lines: z
    .array(
      // Every rule in one place, so each message shows at once rather than one after another.
      z
        .object({
          product: z.custom<ProductPick | null>(() => true),
          supplied: z.string(),
          defective: z.string(),
          frequency: z.string().max(120, "Keep it under 120 characters."),
          remark: z.string().max(500, "Keep it under 500 characters."),
        })
        .superRefine((line, ctx) => {
          if (line.product === null) {
            ctx.addIssue({ code: "custom", path: ["product"], message: "Choose the product." });
          }
          const supplied = QTY_PATTERN.test(line.supplied) ? Number(line.supplied) : null;
          const defective = QTY_PATTERN.test(line.defective) ? Number(line.defective) : null;
          if (supplied === null) {
            ctx.addIssue({
              code: "custom",
              path: ["supplied"],
              message: "Enter the quantity supplied.",
            });
          } else if (supplied <= 0) {
            ctx.addIssue({ code: "custom", path: ["supplied"], message: "More than zero." });
          }
          if (defective === null) {
            ctx.addIssue({
              code: "custom",
              path: ["defective"],
              message: "Enter how many are defective, or 0.",
            });
          } else if (supplied !== null && defective > supplied) {
            ctx.addIssue({
              code: "custom",
              path: ["defective"],
              message: "Not more than supplied.",
            });
          }
        }),
    )
    .min(1, "Add the product the complaint is about.")
    .max(COMPLAINT_LINES_MAX, `At most ${String(COMPLAINT_LINES_MAX)} products.`)
    .superRefine((lines, ctx) => {
      const seen = new Set<string>();
      lines.forEach((line, index) => {
        if (line.product === null) return;
        if (seen.has(line.product.id)) {
          ctx.addIssue({
            code: "custom",
            path: [index, "product"],
            message: "Already listed above.",
          });
        }
        seen.add(line.product.id);
      });
    }),
});

const BLANK_LINE: LineForm = {
  product: null,
  supplied: "",
  defective: "",
  frequency: "",
  remark: "",
};

function orNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

/** The form as a complaint stands, for editing a draft. */
function valuesOf(complaint: Complaint): ComplaintFormValues {
  return {
    typeId: complaint.type.id,
    severity: complaint.severity,
    description: complaint.description,
    contactName: complaint.contactName,
    contactMobile: complaint.contactMobile,
    territory: { id: complaint.territory.id, name: complaint.territory.name, level: "" },
    dealer:
      complaint.partner === null || complaint.partner.hidden
        ? null
        : { id: complaint.partner.id, name: complaint.partner.name ?? "A dealer" },
    dcNo: complaint.dcNo ?? "",
    supplyDate: complaint.supplyDate ?? "",
    regNo: complaint.regNo ?? "",
    pimsNo: complaint.pimsNo ?? "",
    courierDate: complaint.sampleCourierDate ?? "",
    courierDetail: complaint.sampleCourierDetail ?? "",
    lines: complaint.lines.map((line) => ({
      product: {
        id: line.product.id,
        code: null,
        description: line.product.description,
        uom: line.uom ?? "",
        uomDecimals: 3,
        hsnCode: null,
        gstSlab: null,
        packMultiple: null,
      },
      supplied: Number(line.suppliedQty).toString(),
      defective: Number(line.defectiveQty).toString(),
      frequency: line.failureFrequency ?? "",
      remark: line.remark ?? "",
    })),
  };
}

function headerOf(values: ComplaintFormValues): Omit<CreateComplaintRequest, "lines"> {
  return {
    complaint_type_id: values.typeId,
    severity: values.severity,
    description: values.description.trim(),
    contact_name: values.contactName.trim(),
    contact_mobile: normalizeIndianMobile(values.contactMobile) ?? values.contactMobile,
    territory_id: values.territory?.id ?? "",
    partner_id: values.dealer?.id ?? null,
    dc_no: orNull(values.dcNo),
    supply_date: orNull(values.supplyDate),
    reg_no: orNull(values.regNo),
    pims_no: orNull(values.pimsNo),
    sample_courier_date: orNull(values.courierDate),
    sample_courier_detail: orNull(values.courierDetail),
  };
}

function linesOf(values: ComplaintFormValues): CreateComplaintRequest["lines"] {
  return values.lines.map((line) => ({
    product_id: line.product?.id ?? "",
    supplied_qty: line.supplied,
    defective_qty: line.defective,
    failure_frequency: orNull(line.frequency),
    remark: orNull(line.remark),
  }));
}

/** The header fields that differ from the draft as loaded; null when none do. */
const HEADER_KEYS = [
  "complaint_type_id",
  "severity",
  "description",
  "contact_name",
  "contact_mobile",
  "territory_id",
  "partner_id",
  "dc_no",
  "supply_date",
  "reg_no",
  "pims_no",
  "sample_courier_date",
  "sample_courier_detail",
] as const satisfies readonly (keyof PatchComplaintRequest)[];

function headerPatch(
  before: ComplaintFormValues,
  after: ComplaintFormValues,
): PatchComplaintRequest | null {
  const a = headerOf(before);
  const b = headerOf(after);
  const patch: PatchComplaintRequest = {};
  for (const key of HEADER_KEYS) {
    if (a[key] !== b[key]) Object.assign(patch, { [key]: b[key] });
  }
  return Object.keys(patch).length === 0 ? null : patch;
}

/** The backend's field paths onto the form's. */
function formPathOf(path: string): FieldPath<ComplaintFormValues> | null {
  const line = /^lines\.(\d+)\.(product_id|supplied_qty|defective_qty)$/.exec(path);
  if (line !== null) {
    const field = { product_id: "product", supplied_qty: "supplied", defective_qty: "defective" }[
      line[2] ?? "product_id"
    ];
    const index = Number(line[1] ?? 0);
    if (field === "product") return `lines.${index}.product`;
    if (field === "supplied") return `lines.${index}.supplied`;
    return `lines.${index}.defective`;
  }
  const top: Readonly<Record<string, FieldPath<ComplaintFormValues>>> = {
    complaint_type_id: "typeId",
    description: "description",
    contact_name: "contactName",
    contact_mobile: "contactMobile",
    territory_id: "territory",
    dc_no: "dcNo",
    supply_date: "supplyDate",
    sample_courier_date: "courierDate",
  };
  return top[path] ?? null;
}

export interface ComplaintFormProps {
  /** The draft being edited; null for a new complaint. */
  complaint: Complaint | null;
  /** A new complaint about this lead or order (from their pages). */
  about?: { leadId: string | null; orderId: string | null; label: string | null };
}

/**
 * CMPL-003 · Raise a complaint, or edit a draft: what kind and how bad, what went wrong, whom
 * to contact, where the material is installed, the dealer, the challan and supply date
 * (needed to submit), and the products with what was supplied and what is defective (1 to
 * 20, each once). Saved as a draft; submitting is a separate step on the complaint's page.
 */
export function ComplaintForm({ complaint, about }: ComplaintFormProps): React.JSX.Element {
  const router = useRouter();
  const create = useCreateComplaint();
  const saveDraft = useSaveComplaintDraft();
  const headerKey = useIdempotencyKey();
  const linesKey = useIdempotencyKey();
  const [formError, setFormError] = useState<unknown>(null);
  const [initial] = useState<ComplaintFormValues>(() =>
    complaint === null
      ? {
          typeId: "",
          severity: "medium",
          description: "",
          contactName: "",
          contactMobile: "",
          territory: null,
          dealer: null,
          dcNo: "",
          supplyDate: "",
          regNo: "",
          pimsNo: "",
          courierDate: "",
          courierDetail: "",
          lines: [BLANK_LINE],
        }
      : valuesOf(complaint),
  );
  const form = useForm<ComplaintFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: initial,
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const lines = useFieldArray({ control: form.control, name: "lines" });
  const types = useQuery(lookupListQueryOptions("complaint-types"));
  const typeItems = (types.data ?? [])
    .filter((type) => type.isActive || type.id === initial.typeId)
    .map((type) => ({ value: type.id, label: type.name }));

  const submit = useAsyncAction({
    action: async (values: ComplaintFormValues): Promise<Complaint | null> => {
      if (complaint === null) {
        const body: CreateComplaintRequest = {
          ...headerOf(values),
          lead_id: about?.leadId ?? null,
          sales_order_id: about?.orderId ?? null,
          lines: linesOf(values),
        };
        return create.mutateAsync({ body, idempotencyKey: headerKey.keyFor(body) });
      }
      const header = headerPatch(initial, values);
      const before = JSON.stringify(linesOf(initial));
      const nextLines = linesOf(values);
      const linesChanged = JSON.stringify(nextLines) !== before;
      if (header === null && !linesChanged) return null;
      return saveDraft.mutateAsync({
        complaintId: complaint.id,
        header: header === null ? null : { body: header, idempotencyKey: headerKey.keyFor(header) },
        lines: linesChanged
          ? { body: { lines: nextLines }, idempotencyKey: linesKey.keyFor(nextLines) }
          : null,
      });
    },
    logger: log,
    fn: complaint === null ? "handleCreateComplaint" : "handleSaveDraft",
    dataId: "CMPL-003",
    onSuccess: (saved) => {
      const target = saved ?? complaint;
      if (target === null) return;
      if (saved !== null) {
        toast.success(complaint === null ? "Complaint saved as a draft" : "Draft saved", {
          description: "Check it, then submit it for the manager's check.",
        });
      }
      router.push(`/complaints/${target.id}`);
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      const fields = Object.entries(view.fields ?? {}).flatMap(([path, message]) => {
        const field = formPathOf(path);
        return field === null ? [] : [{ field, message }];
      });
      fields.forEach(({ field, message }, index) => {
        form.setError(field, { type: "server", message }, { shouldFocus: index === 0 });
      });
      if (fields.length === 0) setFormError(error);
    },
  });

  const formErrorView = formError === null ? null : toUserFacingError(formError);
  const refusal = formError === null ? null : complaintRefusal(formError);

  return (
    <form
      noValidate
      aria-label={complaint === null ? "New complaint" : "Edit complaint"}
      className="flex flex-col gap-5"
      onSubmit={(event) => {
        setFormError(null);
        void form.handleSubmit((values) => submit.run(values))(event);
      }}
    >
      {about?.label == null ? null : (
        <p className="text-sm text-muted-foreground">About {about.label}.</p>
      )}

      <Card>
        <CardHeader>
          <CardTitle level={3}>What happened</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldGroup className="grid gap-4 sm:grid-cols-2">
            <Controller
              control={form.control}
              name="typeId"
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.error ? true : undefined}>
                  <FieldLabel htmlFor="complaint-type">Type</FieldLabel>
                  <Select
                    items={typeItems}
                    value={field.value === "" ? null : field.value}
                    disabled={types.isPending || types.isError}
                    onValueChange={(next) => {
                      if (typeof next === "string") field.onChange(next);
                    }}
                  >
                    <SelectTrigger
                      id="complaint-type"
                      aria-invalid={fieldState.error ? true : undefined}
                      aria-describedby={fieldState.error ? "complaint-type-error" : undefined}
                    >
                      <SelectValue
                        placeholder={
                          types.isPending
                            ? "Loading…"
                            : types.isError
                              ? "Couldn't load the types"
                              : "Choose a type"
                        }
                      />
                    </SelectTrigger>
                    <SelectContent>
                      {typeItems.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FieldError id="complaint-type-error">{fieldState.error?.message}</FieldError>
                </Field>
              )}
            />
            <Controller
              control={form.control}
              name="severity"
              render={({ field }) => (
                <Field>
                  <FieldLabel htmlFor="complaint-severity">Severity</FieldLabel>
                  <Select
                    items={SEVERITY_ITEMS}
                    value={field.value}
                    onValueChange={(next) => {
                      if (next !== null) field.onChange(next);
                    }}
                  >
                    <SelectTrigger
                      id="complaint-severity"
                      aria-describedby="complaint-severity-hint"
                    >
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {SEVERITY_ITEMS.map((item) => (
                        <SelectItem key={item.value} value={item.value}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FieldDescription id="complaint-severity-hint">
                    It sets how fast it must be answered. The manager may change it.
                  </FieldDescription>
                </Field>
              )}
            />
            <TextField
              form={form}
              name="description"
              label="What went wrong"
              multiline
              className="sm:col-span-2"
            />
          </FieldGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle level={3}>Who and where</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldGroup className="grid gap-4 sm:grid-cols-2">
            <TextField form={form} name="contactName" label="Contact name" autoComplete="name" />
            <TextField
              form={form}
              name="contactMobile"
              label="Contact mobile"
              type="tel"
              inputMode="tel"
              placeholder="98123 45678"
              hint="They get a WhatsApp at each step."
            />
            <Controller
              control={form.control}
              name="territory"
              render={({ field, fieldState }) => (
                <Field data-invalid={fieldState.error ? true : undefined}>
                  <FieldLabel htmlFor="complaint-territory">Where it is installed</FieldLabel>
                  <TerritoryPicker
                    id="complaint-territory"
                    value={field.value}
                    onValueChange={field.onChange}
                    onBlur={field.onBlur}
                    aria-invalid={fieldState.error ? true : undefined}
                    aria-describedby={fieldState.error ? "complaint-territory-error" : undefined}
                  />
                  <FieldError id="complaint-territory-error">
                    {fieldState.error?.message}
                  </FieldError>
                </Field>
              )}
            />
            <Controller
              control={form.control}
              name="dealer"
              render={({ field }) => (
                <Field>
                  <FieldLabel htmlFor="complaint-dealer">
                    Dealer
                    <span className="font-normal text-subtle-foreground">(optional)</span>
                  </FieldLabel>
                  <DealerPicker
                    id="complaint-dealer"
                    value={field.value}
                    onValueChange={field.onChange}
                  />
                </Field>
              )}
            />
          </FieldGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-0.5">
            <CardTitle level={3}>Supply</CardTitle>
            <CardDescription>
              The challan number and supply date are needed to submit.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent>
          <FieldGroup className="grid gap-4 sm:grid-cols-2">
            <TextField form={form} name="dcNo" label="Challan number" optional />
            <TextField form={form} name="supplyDate" label="Supply date" type="date" optional />
            <TextField form={form} name="regNo" label="Registration number" optional />
            <TextField form={form} name="pimsNo" label="PIMS number" optional />
            <TextField form={form} name="courierDate" label="Sample sent on" type="date" optional />
            <TextField form={form} name="courierDetail" label="Courier and docket" optional />
          </FieldGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-0.5">
            <CardTitle level={3}>Products</CardTitle>
            <CardDescription>
              What was supplied, and how much of it is defective. Up to {COMPLAINT_LINES_MAX}.
            </CardDescription>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <ol className="flex flex-col gap-3">
            {lines.fields.map((line, index) => (
              <ProductLine
                key={line.id}
                form={form}
                index={index}
                removable={lines.fields.length > 1}
                onRemove={() => {
                  lines.remove(index);
                }}
              />
            ))}
          </ol>
          {typeof errors.lines?.message === "string" ? (
            <p role="alert" className="text-sm text-danger">
              {errors.lines.message}
            </p>
          ) : null}
          {lines.fields.length < COMPLAINT_LINES_MAX ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="self-start"
              onClick={() => {
                lines.append(BLANK_LINE, { shouldFocus: false });
              }}
            >
              <Icon icon={Add01Icon} />
              Add a product
            </Button>
          ) : null}
        </CardContent>
      </Card>

      {formErrorView === null || refusal === null ? null : (
        <div
          role="alert"
          className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
        >
          <p className="font-medium text-danger">{refusal.title}</p>
          <p className="text-foreground">{refusal.message}</p>
          {formErrorView.reference === undefined ? null : (
            <ErrorReference reference={formErrorView.reference} />
          )}
        </div>
      )}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="outline"
          disabled={submit.isBusy}
          onClick={() => {
            router.back();
          }}
        >
          Cancel
        </Button>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          {complaint === null ? "Save as draft" : "Save draft"}
        </Button>
      </div>
    </form>
  );
}

type FormApi = ReturnType<typeof useForm<ComplaintFormValues>>;
type TextName =
  | "description"
  | "contactName"
  | "contactMobile"
  | "dcNo"
  | "supplyDate"
  | "regNo"
  | "pimsNo"
  | "courierDate"
  | "courierDetail";

function TextField({
  form,
  name,
  label,
  optional = false,
  multiline = false,
  hint,
  className,
  ...input
}: {
  form: FormApi;
  name: TextName;
  label: string;
  optional?: boolean;
  multiline?: boolean;
  hint?: string;
  className?: string;
  type?: string;
  inputMode?: "tel" | "text";
  placeholder?: string;
  autoComplete?: string;
}): React.JSX.Element {
  const { errors } = useFormState({ control: form.control, name });
  const error = errors[name]?.message;
  const id = `complaint-${name}`;
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined;
  return (
    <Field data-invalid={error ? true : undefined} className={className}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-subtle-foreground">(optional)</span> : null}
      </FieldLabel>
      {multiline ? (
        <Textarea
          id={id}
          rows={3}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...form.register(name)}
        />
      ) : (
        <Input
          id={id}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          {...input}
          {...form.register(name)}
        />
      )}
      {hint && !error ? <FieldDescription id={`${id}-hint`}>{hint}</FieldDescription> : null}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}

function ProductLine({
  form,
  index,
  removable,
  onRemove,
}: {
  form: FormApi;
  index: number;
  removable: boolean;
  onRemove: () => void;
}): React.JSX.Element {
  const { errors } = useFormState({ control: form.control, name: `lines.${index}` });
  const lineErrors = errors.lines?.[index];
  const prefix = `complaint-line-${String(index)}`;
  const number = index + 1;

  return (
    <li className="flex flex-col gap-3 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-muted-foreground">Product {number}</span>
        {removable ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={`Remove product ${String(number)}`}
            onClick={onRemove}
          >
            <Icon icon={Delete02Icon} />
          </Button>
        ) : null}
      </div>
      <Controller
        control={form.control}
        name={`lines.${index}.product`}
        render={({ field, fieldState }) => (
          <Field data-invalid={fieldState.error ? true : undefined}>
            <FieldLabel htmlFor={`${prefix}-product`}>Product</FieldLabel>
            <ProductPicker
              id={`${prefix}-product`}
              value={field.value}
              onValueChange={field.onChange}
              aria-invalid={fieldState.error ? true : undefined}
              aria-describedby={fieldState.error ? `${prefix}-product-error` : undefined}
            />
            <FieldError id={`${prefix}-product-error`}>{fieldState.error?.message}</FieldError>
          </Field>
        )}
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <Field data-invalid={lineErrors?.supplied ? true : undefined}>
          <FieldLabel htmlFor={`${prefix}-supplied`}>Supplied</FieldLabel>
          <Input
            id={`${prefix}-supplied`}
            inputMode="decimal"
            aria-invalid={lineErrors?.supplied ? true : undefined}
            aria-describedby={lineErrors?.supplied ? `${prefix}-supplied-error` : undefined}
            {...form.register(`lines.${index}.supplied`)}
          />
          <FieldError id={`${prefix}-supplied-error`}>{lineErrors?.supplied?.message}</FieldError>
        </Field>
        <Field data-invalid={lineErrors?.defective ? true : undefined}>
          <FieldLabel htmlFor={`${prefix}-defective`}>Defective</FieldLabel>
          <Input
            id={`${prefix}-defective`}
            inputMode="decimal"
            aria-invalid={lineErrors?.defective ? true : undefined}
            aria-describedby={lineErrors?.defective ? `${prefix}-defective-error` : undefined}
            {...form.register(`lines.${index}.defective`)}
          />
          <FieldError id={`${prefix}-defective-error`}>{lineErrors?.defective?.message}</FieldError>
        </Field>
        <Field>
          <FieldLabel htmlFor={`${prefix}-frequency`}>
            How often it fails
            <span className="font-normal text-subtle-foreground">(optional)</span>
          </FieldLabel>
          <Input
            id={`${prefix}-frequency`}
            placeholder="every 3 to 4 m"
            {...form.register(`lines.${index}.frequency`)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor={`${prefix}-remark`}>
            Remark
            <span className="font-normal text-subtle-foreground">(optional)</span>
          </FieldLabel>
          <Input id={`${prefix}-remark`} {...form.register(`lines.${index}.remark`)} />
        </Field>
      </div>
    </li>
  );
}
