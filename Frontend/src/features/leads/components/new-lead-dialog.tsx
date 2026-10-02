"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon } from "@hugeicons/core-free-icons";
import { parseAsBoolean, useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState, type DefaultValues } from "react-hook-form";
import { toast } from "sonner";

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
  LEAD_INQUIRY_TYPES,
  LEAD_TERRITORY_LEVELS,
  MAX_LEAD_CROPS,
  type CreateLeadFormValues,
  type CreateLeadRequest,
} from "@/features/leads/api/leads.schemas";
import { createLeadFieldErrors } from "@/features/leads/lib/create-lead-errors";
import { LEAD_INQUIRY_TYPE_LABELS, describeCreatedLead } from "@/features/leads/lib/lead-labels";
import { CropPicker } from "@/features/lookups/components/crop-picker";
import { LookupSelect } from "@/features/lookups/components/lookup-select";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { createRequestId } from "@/lib/api/request-id";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/leads/components/new-lead-dialog.tsx",
  dataId: "LEAD-002",
});

const EMPTY_FORM: DefaultValues<CreateLeadFormValues> = {
  customerName: "",
  phone: "",
  email: "",
  territory: null,
  village: "",
  source: null,
  estimatedValue: "",
  crops: [],
  landAcres: "",
  note: "",
};

const TYPE_ITEMS = LEAD_INQUIRY_TYPES.map((value) => ({
  value,
  label: LEAD_INQUIRY_TYPE_LABELS[value],
}));

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
 * LEAD-002 · New lead. Open state lives in the URL (?newLead=true), so the command menu and
 * links can open it. Validation runs on blur, then on change; server field errors (422) land
 * on the matching field; anything else shows an inline error with a copyable reference.
 *
 * Retrying the same details reuses the Idempotency-Key, so a save whose reply was lost is
 * replayed by the backend instead of creating the lead twice. Changing any detail makes a
 * new key. Duplicates are never refused: the backend flags them, and the toast says so.
 */
export function NewLeadDialog(): React.JSX.Element {
  const [open, setOpen] = useQueryState("newLead", parseAsBoolean.withDefault(false));
  const [formError, setFormError] = useState<unknown>(null);
  const lastAttempt = useRef<{ body: string; key: string } | null>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const createLead = useCreateLead();
  const form = useForm<CreateLeadFormValues, unknown, CreateLeadRequest>({
    resolver: zodResolver(createLeadFormSchema),
    defaultValues: EMPTY_FORM,
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  // The dialog can be left before the success check has had its moment; the timer must not
  // outlive it, or it resets a form that is gone and writes to another page's URL.
  useEffect(() => {
    return () => {
      window.clearTimeout(closeTimer.current);
    };
  }, []);

  const idempotencyKeyFor = (body: CreateLeadRequest): string => {
    const serialized = JSON.stringify(body);
    if (lastAttempt.current?.body !== serialized) {
      lastAttempt.current = { body: serialized, key: createRequestId() };
    }
    return lastAttempt.current.key;
  };

  const applyServerFieldErrors = (error: unknown): boolean => {
    const fieldErrors = createLeadFieldErrors(error);
    fieldErrors.forEach(({ field, message }, index) => {
      form.setError(field, { type: "server", message }, { shouldFocus: index === 0 });
    });
    return fieldErrors.length > 0;
  };

  const resetForm = (): void => {
    window.clearTimeout(closeTimer.current);
    form.reset(EMPTY_FORM);
    lastAttempt.current = null;
  };

  const submit = useAsyncAction({
    action: (body: CreateLeadRequest) =>
      createLead.mutateAsync({ body, idempotencyKey: idempotencyKeyFor(body) }),
    logger: log,
    fn: "handleCreateLead",
    dataId: "LEAD-002",
    onSuccess: (lead) => {
      toast.success("Lead created", { description: describeCreatedLead(lead) });
      closeTimer.current = window.setTimeout(() => {
        void setOpen(false);
        resetForm();
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
      resetForm();
      setFormError(null);
      submit.reset();
    }
    void setOpen(next);
  };

  const onValid = (body: CreateLeadRequest): void => {
    setFormError(null);
    void submit.run(body);
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
              Capture the enquiry now. Quotations can be added later.
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            <FieldGroup className="grid gap-4 sm:grid-cols-2">
              <FormField
                id="lead-customer-name"
                label="Farmer name"
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

              <FormField id="lead-email" label="Email" optional error={errors.email?.message}>
                {(aria) => (
                  <Input
                    type="email"
                    inputMode="email"
                    autoComplete="email"
                    {...aria}
                    {...form.register("email")}
                  />
                )}
              </FormField>

              <Controller
                control={form.control}
                name="territory"
                render={({ field, fieldState }) => (
                  <FormField
                    id="lead-territory"
                    label="Territory"
                    description="The district, taluka or village the farmer is in. It decides which office gets the lead."
                    error={fieldState.error?.message}
                    className="sm:col-span-2"
                  >
                    {(aria) => (
                      <TerritoryPicker
                        {...aria}
                        value={field.value ?? null}
                        levels={LEAD_TERRITORY_LEVELS}
                        onValueChange={(territory) => {
                          field.onChange(territory);
                        }}
                        onBlur={field.onBlur}
                      />
                    )}
                  </FormField>
                )}
              />

              <FormField id="lead-village" label="Village" optional error={errors.village?.message}>
                {(aria) => (
                  <Input autoComplete="address-level3" {...aria} {...form.register("village")} />
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

              <Controller
                control={form.control}
                name="type"
                render={({ field, fieldState }) => (
                  <FormField id="lead-type" label="Inquiry type" error={fieldState.error?.message}>
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
                        <SelectTrigger {...aria}>
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

              <Controller
                control={form.control}
                name="misSystem"
                render={({ field, fieldState }) => (
                  <FormField
                    id="lead-mis-system"
                    label="Irrigation system"
                    error={fieldState.error?.message}
                  >
                    {(aria) => (
                      <LookupSelect
                        {...aria}
                        list="mis-systems"
                        placeholder="Choose a system"
                        value={field.value ?? null}
                        onValueChange={field.onChange}
                      />
                    )}
                  </FormField>
                )}
              />

              <Controller
                control={form.control}
                name="source"
                render={({ field, fieldState }) => (
                  <FormField
                    id="lead-source"
                    label="Source"
                    optional
                    description="Left empty, it's recorded from who you are: Employee for staff."
                    error={fieldState.error?.message}
                    className="sm:col-span-2"
                  >
                    {(aria) => (
                      <LookupSelect
                        {...aria}
                        list="lead-sources"
                        clearable
                        placeholder="Where the enquiry came from"
                        value={field.value ?? null}
                        onValueChange={field.onChange}
                      />
                    )}
                  </FormField>
                )}
              />

              <Controller
                control={form.control}
                name="crops"
                render={({ field, fieldState }) => (
                  <FormField
                    id="lead-crops"
                    label="Crops"
                    optional
                    description="Up to 10."
                    error={fieldState.error?.message}
                  >
                    {(aria) => (
                      <CropPicker
                        {...aria}
                        max={MAX_LEAD_CROPS}
                        value={field.value ?? []}
                        onValueChange={field.onChange}
                      />
                    )}
                  </FormField>
                )}
              />

              <FormField
                id="lead-land"
                label="Land"
                optional
                description="In acres, e.g. 4.5."
                error={errors.landAcres?.message}
              >
                {(aria) => (
                  <InputGroup>
                    <InputGroupInput
                      inputMode="decimal"
                      placeholder="4.5"
                      {...aria}
                      {...form.register("landAcres")}
                    />
                    <InputGroupAddon align="end">acres</InputGroupAddon>
                  </InputGroup>
                )}
              </FormField>

              <FormField
                id="lead-note"
                label="Note"
                optional
                description="Becomes the first entry on the lead's timeline."
                error={errors.note?.message}
                className="sm:col-span-2"
              >
                {(aria) => <Textarea rows={3} {...aria} {...form.register("note")} />}
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
