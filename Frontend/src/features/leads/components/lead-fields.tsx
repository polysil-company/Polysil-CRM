"use client";

import type * as React from "react";
import { Controller, useFormState, type UseFormReturn } from "react-hook-form";

import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
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
import {
  LEAD_INQUIRY_TYPES,
  LEAD_TERRITORY_LEVELS,
  MAX_LEAD_CROPS,
  type CreateLeadFormValues,
  type CreateLeadRequest,
} from "@/features/leads/api/leads.schemas";
import { LEAD_INQUIRY_TYPE_LABELS } from "@/features/leads/lib/lead-labels";
import { CropPicker } from "@/features/lookups/components/crop-picker";
import { LookupSelect } from "@/features/lookups/components/lookup-select";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";

const TYPE_ITEMS = LEAD_INQUIRY_TYPES.map((value) => ({
  value,
  label: LEAD_INQUIRY_TYPE_LABELS[value],
}));

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
 * LEAD-002, LEAD-010 · A lead's own fields, shared by New lead and Edit lead: who, where, what
 * they want, and how big. `withNote` adds the first note, which only a new lead takes.
 */
export function LeadFields({
  form,
  idPrefix,
  withNote = false,
}: {
  form: UseFormReturn<CreateLeadFormValues, unknown, CreateLeadRequest>;
  idPrefix: string;
  withNote?: boolean;
}): React.JSX.Element {
  const { errors } = useFormState({ control: form.control });
  return (
    <FieldGroup className="grid gap-4 sm:grid-cols-2">
      <FormField
        id={`${idPrefix}-customer-name`}
        label="Farmer name"
        error={errors.customerName?.message}
        className="sm:col-span-2"
      >
        {(aria) => <Input autoComplete="name" {...aria} {...form.register("customerName")} />}
      </FormField>

      <FormField id={`${idPrefix}-phone`} label="Mobile number" error={errors.phone?.message}>
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

      <FormField id={`${idPrefix}-email`} label="Email" optional error={errors.email?.message}>
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
            id={`${idPrefix}-territory`}
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

      <FormField
        id={`${idPrefix}-village`}
        label="Village"
        optional
        error={errors.village?.message}
      >
        {(aria) => <Input autoComplete="address-level3" {...aria} {...form.register("village")} />}
      </FormField>

      <FormField
        id={`${idPrefix}-value`}
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
          <FormField id={`${idPrefix}-type`} label="Inquiry type" error={fieldState.error?.message}>
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
            id={`${idPrefix}-mis-system`}
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
            id={`${idPrefix}-source`}
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
            id={`${idPrefix}-crops`}
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
        id={`${idPrefix}-land`}
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

      {withNote ? (
        <FormField
          id={`${idPrefix}-note`}
          label="Note"
          optional
          description="Becomes the first entry on the lead's timeline."
          error={errors.note?.message}
          className="sm:col-span-2"
        >
          {(aria) => <Textarea rows={3} {...aria} {...form.register("note")} />}
        </FormField>
      ) : null}
    </FieldGroup>
  );
}
