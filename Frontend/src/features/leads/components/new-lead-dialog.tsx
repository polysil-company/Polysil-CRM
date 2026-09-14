"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon } from "@hugeicons/core-free-icons";
import { parseAsBoolean, useQueryState } from "nuqs";
import { useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState, type DefaultValues } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { ErrorReference } from "@/components/patterns/error-state";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCreateLead } from "@/features/leads/api/leads.mutations";
import {
  createLeadFormSchema,
  LEAD_SOURCES,
  ORDER_TYPES,
  type CreateLeadFormValues,
  type CreateLeadRequest,
} from "@/features/leads/api/leads.schemas";
import { LEAD_SOURCE_LABELS, ORDER_TYPE_LABELS } from "@/features/leads/lib/lead-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/leads/components/new-lead-dialog.tsx",
  dataId: "LEAD-002",
});

const EMPTY_FORM: DefaultValues<CreateLeadFormValues> = {
  customerName: "",
  phone: "",
  village: "",
  district: "",
  state: "",
  estimatedValue: "",
  notes: "",
};

const FORM_FIELDS = [
  "customerName",
  "phone",
  "village",
  "district",
  "state",
  "source",
  "type",
  "estimatedValue",
  "notes",
] as const;

/** 422 body agreed for field-level errors: `details: { fields: { phone: "…" } }`. */
const serverFieldErrorsSchema = z.object({ fields: z.record(z.string(), z.string()) });

const SOURCE_ITEMS = LEAD_SOURCES.map((value) => ({ value, label: LEAD_SOURCE_LABELS[value] }));
const TYPE_ITEMS = ORDER_TYPES.map((value) => ({ value, label: ORDER_TYPE_LABELS[value] }));

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 700;

interface FieldAria {
  id: string;
  "aria-invalid": true | undefined;
  "aria-describedby": string | undefined;
}

function FormField({
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
  const describedBy = error ? errorId : description ? descriptionId : undefined;

  return (
    <Field data-invalid={error ? true : undefined} className={className}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-subtle-foreground">(optional)</span> : null}
      </FieldLabel>
      {children({ id, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy })}
      {description && !error ? (
        <FieldDescription id={descriptionId}>{description}</FieldDescription>
      ) : null}
      <FieldError id={errorId}>{error}</FieldError>
    </Field>
  );
}

/**
 * LEAD-002 · New lead. Open state lives in the URL (?newLead=true), so the
 * command menu and links can open it. Validation runs on blur, then on change;
 * server field errors (422) land on the matching field; anything else shows an
 * inline error with a copyable reference.
 */
export function NewLeadDialog(): React.JSX.Element {
  const [open, setOpen] = useQueryState("newLead", parseAsBoolean.withDefault(false));
  const [formError, setFormError] = useState<unknown>(null);
  const createLead = useCreateLead();
  const form = useForm<CreateLeadFormValues, unknown, CreateLeadRequest>({
    resolver: zodResolver(createLeadFormSchema),
    defaultValues: EMPTY_FORM,
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  const applyServerFieldErrors = (error: unknown): boolean => {
    if (!isApiError(error) || error.status !== 422) {
      return false;
    }
    const parsed = serverFieldErrorsSchema.safeParse(error.details);
    if (!parsed.success) {
      return false;
    }
    let applied = false;
    for (const [name, message] of Object.entries(parsed.data.fields)) {
      const field = FORM_FIELDS.find((candidate) => candidate === name);
      if (field !== undefined) {
        form.setError(field, { type: "server", message }, { shouldFocus: !applied });
        applied = true;
      }
    }
    return applied;
  };

  const submit = useAsyncAction({
    action: (input: CreateLeadRequest) => createLead.mutateAsync(input),
    logger: log,
    fn: "handleCreateLead",
    dataId: "LEAD-002",
    onSuccess: (lead) => {
      toast.success("Lead created", { description: `${lead.customerName} · ${lead.code}` });
      window.setTimeout(() => {
        void setOpen(false);
        form.reset(EMPTY_FORM);
      }, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      if (!applyServerFieldErrors(error)) {
        setFormError(error);
      }
    },
  });

  const handleOpenChange = (next: boolean): void => {
    if (submit.isBusy) {
      return; // Never close in the middle of a save.
    }
    if (!next) {
      form.reset(EMPTY_FORM);
      setFormError(null);
      submit.reset();
    }
    void setOpen(next);
  };

  const onValid = (values: CreateLeadRequest): void => {
    setFormError(null);
    void submit.run(values);
  };

  const formErrorView = formError === null ? null : toUserFacingError(formError);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button />}>
        <Icon icon={Add01Icon} />
        New lead
      </DialogTrigger>
      <DialogContent>
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            void form.handleSubmit(onValid)(event);
          }}
        >
          <DialogHeader>
            <DialogTitle>New lead</DialogTitle>
            <DialogDescription>
              Capture the enquiry now — quotations can be added later.
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            <FieldGroup className="grid gap-4 sm:grid-cols-2">
              <FormField
                id="lead-customer-name"
                label="Customer name"
                error={errors.customerName?.message}
                className="sm:col-span-2"
              >
                {(aria) => (
                  <Input autoComplete="name" {...aria} {...form.register("customerName")} />
                )}
              </FormField>

              <FormField id="lead-phone" label="Mobile number" error={errors.phone?.message}>
                {(aria) => (
                  <Input
                    type="tel"
                    inputMode="tel"
                    autoComplete="tel"
                    placeholder="98123 45678"
                    {...aria}
                    {...form.register("phone")}
                  />
                )}
              </FormField>

              <FormField
                id="lead-value"
                label="Estimated value"
                optional
                description="In rupees, without commas."
                error={errors.estimatedValue?.message}
              >
                {(aria) => (
                  <InputGroup>
                    <InputGroupAddon>₹</InputGroupAddon>
                    <InputGroupInput
                      inputMode="decimal"
                      placeholder="125000"
                      {...aria}
                      {...form.register("estimatedValue")}
                    />
                  </InputGroup>
                )}
              </FormField>

              <FormField id="lead-village" label="Village" optional error={errors.village?.message}>
                {(aria) => (
                  <Input autoComplete="address-level3" {...aria} {...form.register("village")} />
                )}
              </FormField>

              <FormField id="lead-district" label="District" error={errors.district?.message}>
                {(aria) => (
                  <Input autoComplete="address-level2" {...aria} {...form.register("district")} />
                )}
              </FormField>

              <FormField id="lead-state" label="State" error={errors.state?.message}>
                {(aria) => (
                  <Input autoComplete="address-level1" {...aria} {...form.register("state")} />
                )}
              </FormField>

              <Controller
                control={form.control}
                name="source"
                render={({ field, fieldState }) => (
                  <FormField id="lead-source" label="Source" error={fieldState.error?.message}>
                    {(aria) => (
                      <Select
                        items={SOURCE_ITEMS}
                        value={field.value ?? null}
                        onValueChange={(value) => {
                          if (value !== null) {
                            field.onChange(value);
                          }
                        }}
                      >
                        <SelectTrigger {...aria} onBlur={field.onBlur}>
                          <SelectValue placeholder="Choose a source" />
                        </SelectTrigger>
                        <SelectContent>
                          {SOURCE_ITEMS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </FormField>
                )}
              />

              <Controller
                control={form.control}
                name="type"
                render={({ field, fieldState }) => (
                  <FormField id="lead-type" label="Order type" error={fieldState.error?.message}>
                    {(aria) => (
                      <Select
                        items={TYPE_ITEMS}
                        value={field.value ?? null}
                        onValueChange={(value) => {
                          if (value !== null) {
                            field.onChange(value);
                          }
                        }}
                      >
                        <SelectTrigger {...aria} onBlur={field.onBlur}>
                          <SelectValue placeholder="Choose a type" />
                        </SelectTrigger>
                        <SelectContent>
                          {TYPE_ITEMS.map((item) => (
                            <SelectItem key={item.value} value={item.value}>
                              {item.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  </FormField>
                )}
              />

              <FormField
                id="lead-notes"
                label="Notes"
                optional
                error={errors.notes?.message}
                className="sm:col-span-2"
              >
                {(aria) => <Textarea rows={3} {...aria} {...form.register("notes")} />}
              </FormField>
            </FieldGroup>

            {formErrorView ? (
              <div
                role="alert"
                className="mt-4 flex flex-col gap-2 rounded-md border border-border bg-danger-soft p-3 text-sm"
              >
                <p className="font-medium text-danger">{formErrorView.title}</p>
                <p className="text-muted-foreground">{formErrorView.description}</p>
                {formErrorView.reference ? (
                  <ErrorReference reference={formErrorView.reference} className="self-start" />
                ) : null}
              </div>
            ) : null}
          </DialogBody>

          <DialogFooter>
            <DialogClose
              render={<Button type="button" variant="outline" disabled={submit.isBusy} />}
            >
              Cancel
            </DialogClose>
            <Button
              type="submit"
              state={submit.state}
              loadingLabel="Creating…"
              successLabel="Created"
              errorLabel="Not saved"
            >
              Create lead
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
