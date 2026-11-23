"use client";

import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { usePatchCustomer } from "@/features/customers/api/customers.mutations";
import {
  CUSTOMER_TYPES,
  type CustomerDetail,
  type CustomerPatchRequest,
  type CustomerType,
} from "@/features/customers/api/customers.schemas";
import { CUSTOMER_TYPE_LABELS } from "@/features/customers/lib/customer-labels";
import type { TerritoryChoice } from "@/features/lookups/api/lookups.schemas";
import { TerritoryPicker } from "@/features/lookups/components/territory-picker";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { readFieldErrors } from "@/lib/api/errors";
import { formatIndianPhone } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/customers/components/customer-edit-dialog.tsx",
  dataId: "LEAD-018",
});

/** What the form holds, as typed. */
export interface CustomerDraft {
  readonly type: CustomerType;
  readonly name: string;
  readonly email: string;
  readonly territory: TerritoryChoice | null;
  readonly village: string;
  readonly address: string;
  readonly surveyNo: string;
}

export function draftOf(customer: CustomerDetail): CustomerDraft {
  return {
    type: customer.type,
    name: customer.name,
    email: customer.email ?? "",
    territory: customer.territory,
    village: customer.village ?? "",
    address: customer.address ?? "",
    surveyNo: customer.surveyNo ?? "",
  };
}

function orNull(value: string): string | null {
  return value.trim() === "" ? null : value.trim();
}

/** Only what changed, as PATCH takes it. Editing never touches the leads or documents. */
export function patchOf(customer: CustomerDetail, draft: CustomerDraft): CustomerPatchRequest {
  return {
    ...(draft.type === customer.type ? {} : { customer_type: draft.type }),
    ...(draft.name.trim() === customer.name ? {} : { name: draft.name.trim() }),
    ...(orNull(draft.email) === customer.email ? {} : { email: orNull(draft.email) }),
    ...(draft.territory === null || draft.territory.id === customer.territory?.id
      ? {}
      : { territory_id: draft.territory.id }),
    ...(orNull(draft.village) === customer.village ? {} : { village: orNull(draft.village) }),
    ...(orNull(draft.address) === customer.address ? {} : { address: orNull(draft.address) }),
    ...(orNull(draft.surveyNo) === customer.surveyNo ? {} : { survey_no: orNull(draft.surveyNo) }),
  };
}

type Field = "name" | "email" | "territory";

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function draftProblems(draft: CustomerDraft): Partial<Record<Field, string>> {
  return {
    ...(draft.name.trim() === "" ? { name: "Enter the customer's name." } : {}),
    ...(draft.email.trim() !== "" && !EMAIL_PATTERN.test(draft.email.trim())
      ? { email: "An email like name@example.com, or leave it empty." }
      : {}),
  };
}

const WIRE_FIELDS: Readonly<Record<string, Field>> = {
  name: "name",
  email: "email",
  territory_id: "territory",
};

/** LEAD-018 · Correct a customer's details. The mobile is its identity and stays. */
export function CustomerEditForm({
  customer,
  onDone,
}: {
  customer: CustomerDetail;
  onDone: () => void;
}): React.JSX.Element {
  const [draft, setDraft] = useState<CustomerDraft>(() => draftOf(customer));
  const [problems, setProblems] = useState<Partial<Record<Field, string>>>({});
  const mutation = usePatchCustomer();
  const idempotency = useIdempotencyKey();
  const changes = patchOf(customer, draft);
  const nothingChanged = Object.keys(changes).length === 0;

  const save = useAsyncAction({
    action: () =>
      mutation.mutateAsync({
        customerId: customer.id,
        body: changes,
        idempotencyKey: idempotency.keyFor({ id: customer.id, ...changes }),
      }),
    logger: log,
    fn: "handlePatchCustomer",
    dataId: "LEAD-018",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success("Customer saved", { description: saved.name });
      onDone();
    },
    onError: (error) => {
      const mapped: Partial<Record<Field, string>> = {};
      for (const [wire, message] of Object.entries(readFieldErrors(error) ?? {})) {
        const field = WIRE_FIELDS[wire];
        if (field !== undefined) mapped[field] = message;
      }
      if (Object.keys(mapped).length > 0) {
        setProblems(mapped);
        return;
      }
      toast.error("Customer not saved", { description: toUserFacingError(error).description });
    },
  });

  const set = (next: Partial<CustomerDraft>): void => {
    setDraft((before) => ({ ...before, ...next }));
  };
  const invalid = (field: Field): true | undefined =>
    problems[field] === undefined ? undefined : true;
  const types = CUSTOMER_TYPES.map((type) => ({ value: type, label: CUSTOMER_TYPE_LABELS[type] }));

  return (
    <form
      noValidate
      aria-label={`Edit ${customer.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        const found = draftProblems(draft);
        setProblems(found);
        if (Object.keys(found).length === 0) void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Edit {customer.name}</DialogTitle>
        <DialogDescription>
          The mobile, {formatIndianPhone(customer.mobile)}, is who the customer is and stays. Its
          leads, quotations and orders don&apos;t change.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field data-invalid={invalid("name")}>
            <FieldLabel htmlFor="customer-name">Name</FieldLabel>
            <Input
              id="customer-name"
              value={draft.name}
              maxLength={200}
              autoComplete="name"
              aria-invalid={invalid("name")}
              aria-describedby={invalid("name") ? "customer-name-error" : undefined}
              onChange={(event) => {
                set({ name: event.target.value });
              }}
            />
            <FieldError id="customer-name-error">{problems.name}</FieldError>
          </Field>
          <Field>
            <FieldLabel htmlFor="customer-type">Type</FieldLabel>
            <Select
              items={types}
              value={draft.type}
              onValueChange={(next) => {
                const type = CUSTOMER_TYPES.find((item) => item === next);
                if (type !== undefined) set({ type });
              }}
            >
              <SelectTrigger id="customer-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {types.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
        </div>
        <Field data-invalid={invalid("email")}>
          <FieldLabel htmlFor="customer-email">
            Email <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          <Input
            id="customer-email"
            type="email"
            inputMode="email"
            autoComplete="email"
            value={draft.email}
            aria-invalid={invalid("email")}
            aria-describedby={invalid("email") ? "customer-email-error" : undefined}
            onChange={(event) => {
              set({ email: event.target.value });
            }}
          />
          <FieldError id="customer-email-error">{problems.email}</FieldError>
        </Field>
        <Field data-invalid={invalid("territory")}>
          <FieldLabel htmlFor="customer-territory">Area</FieldLabel>
          <TerritoryPicker
            id="customer-territory"
            value={draft.territory}
            levels={["district", "taluka", "village"]}
            onValueChange={(territory) => {
              set({ territory });
            }}
            aria-invalid={invalid("territory")}
            aria-describedby={invalid("territory") ? "customer-territory-error" : undefined}
          />
          <FieldError id="customer-territory-error">{problems.territory}</FieldError>
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="customer-village">
              Village <span className="font-normal text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Input
              id="customer-village"
              value={draft.village}
              maxLength={120}
              onChange={(event) => {
                set({ village: event.target.value });
              }}
            />
          </Field>
          <Field>
            <FieldLabel htmlFor="customer-survey">
              Survey no. <span className="font-normal text-muted-foreground">(optional)</span>
            </FieldLabel>
            <Input
              id="customer-survey"
              value={draft.surveyNo}
              maxLength={60}
              onChange={(event) => {
                set({ surveyNo: event.target.value });
              }}
            />
          </Field>
        </div>
        <Field>
          <FieldLabel htmlFor="customer-address">
            Address <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="customer-address"
            rows={2}
            value={draft.address}
            maxLength={500}
            onChange={(event) => {
              set({ address: event.target.value });
            }}
          />
        </Field>
      </DialogBody>
      <DialogFooter>
        {nothingChanged ? (
          <span className="mr-auto text-xs text-muted-foreground">Nothing changed yet.</span>
        ) : null}
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          disabled={nothingChanged}
          state={save.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save
        </Button>
      </DialogFooter>
    </form>
  );
}
