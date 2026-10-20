"use client";

import type * as React from "react";

import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import type { OrderSubsidyRequest } from "@/features/orders/api/orders.schemas";
import { readFieldErrors } from "@/lib/api/errors";
import { formatInr } from "@/lib/format";

import { SubsidyLeadsPicker, type SubsidyLead } from "./subsidy-leads-picker";

/**
 * SO-008 · A subsidised order's subsidy as a form keeps it (FS-054): the leads, then the
 * material (empty for the order total), the subsidy, and the farmer payable (empty for
 * material less subsidy). Used by the new-order screen and the order's Edit the subsidy.
 */
export interface SubsidyDraft {
  readonly leads: readonly SubsidyLead[];
  readonly material: string;
  readonly amount: string;
  readonly payable: string;
}

export type SubsidyField = "lead_ids" | "material_amount" | "subsidy_amount" | "farmer_payable";
export type SubsidyProblems = Partial<Record<SubsidyField, string>>;

/** "12.50" with at most two decimals, never negative; null when it is one. */
export function moneyProblem(value: string): string | null {
  return /^\d+(\.\d{1,2})?$/.test(value.trim()) ? null : "Enter rupees, like 49000 or 49000.50.";
}

/** What the screen can tell before asking the backend: the shape, not the amounts' limits. */
export function subsidyDraftProblems(draft: SubsidyDraft): SubsidyProblems {
  const problems: SubsidyProblems = {};
  if (draft.leads.length === 0) problems.lead_ids = "Add the farmer's lead.";
  const material = draft.material.trim() === "" ? null : moneyProblem(draft.material);
  if (material !== null) problems.material_amount = material;
  const amount = draft.amount.trim() === "" ? "Enter the subsidy." : moneyProblem(draft.amount);
  if (amount !== null) problems.subsidy_amount = amount;
  const payable = draft.payable.trim() === "" ? null : moneyProblem(draft.payable);
  if (payable !== null) problems.farmer_payable = payable;
  return problems;
}

/** The request body: empty amounts are left out, so the backend works them out. */
export function subsidyRequest(draft: SubsidyDraft): OrderSubsidyRequest {
  return {
    lead_ids: draft.leads.map((lead) => lead.id),
    subsidy_amount: draft.amount.trim(),
    ...(draft.material.trim() === "" ? {} : { material_amount: draft.material.trim() }),
    ...(draft.payable.trim() === "" ? {} : { farmer_payable: draft.payable.trim() }),
  };
}

/** The backend names subsidy fields `subsidy.<field>` (or bare, on PUT /orders/{id}/subsidy). */
export function subsidyFieldErrors(error: unknown): SubsidyProblems {
  const fields = readFieldErrors(error) ?? {};
  const problems: SubsidyProblems = {};
  for (const field of [
    "lead_ids",
    "material_amount",
    "subsidy_amount",
    "farmer_payable",
  ] as const) {
    const named = fields[`subsidy.${field}`] ?? fields[field];
    if (named !== undefined) problems[field] = named;
  }
  // `lead_ids` names the lead's id; say what is wrong with it instead
  if (problems.lead_ids !== undefined) {
    problems.lead_ids = "A lead you named can't take this order. Remove it, or pick another.";
  }
  return problems;
}

/**
 * The leads and the three amounts. `total` is the order total now, for the hints; null while
 * the items aren't priced.
 */
export function SubsidyFields({
  idPrefix,
  draft,
  onDraftChange,
  problems,
  total,
  firstLeadFixed = false,
  stacked = false,
}: {
  idPrefix: string;
  draft: SubsidyDraft;
  onDraftChange: (next: SubsidyDraft) => void;
  problems: SubsidyProblems;
  total: string | null;
  firstLeadFixed?: boolean;
  /** One amount under another, for a narrow dialog. */
  stacked?: boolean;
}): React.JSX.Element {
  const base = draft.material.trim() === "" ? total : draft.material.trim();
  const derived =
    base !== null && moneyProblem(base) === null && moneyProblem(draft.amount) === null
      ? Number(base) - Number(draft.amount)
      : null;
  const leadsId = `${idPrefix}-leads`;

  return (
    <div className="flex flex-col gap-4">
      <Field data-invalid={problems.lead_ids === undefined ? undefined : true}>
        <FieldLabel htmlFor={leadsId}>Leads</FieldLabel>
        <SubsidyLeadsPicker
          id={leadsId}
          leads={draft.leads}
          onLeadsChange={(leads) => {
            onDraftChange({ ...draft, leads });
          }}
          firstFixed={firstLeadFixed}
          invalid={problems.lead_ids !== undefined}
          describedBy={problems.lead_ids === undefined ? `${leadsId}-hint` : `${leadsId}-error`}
        />
        {problems.lead_ids === undefined ? (
          <FieldDescription id={`${leadsId}-hint`}>
            {firstLeadFixed
              ? "The first lead routes the order and stays first. Add or remove the others."
              : "The farmers the subsidy is for, qualified or later. The first is the order's lead and can't change later."}
          </FieldDescription>
        ) : null}
        <FieldError id={`${leadsId}-error`}>{problems.lead_ids}</FieldError>
      </Field>
      <div className={stacked ? "flex flex-col gap-4" : "grid gap-4 sm:grid-cols-3"}>
        <MoneyInput
          id={`${idPrefix}-material`}
          label="Material amount"
          optional
          placeholder={
            total === null ? "The order total" : `Order total, ${formatInr(total, { paise: true })}`
          }
          value={draft.material}
          error={problems.material_amount}
          onChange={(material) => {
            onDraftChange({ ...draft, material });
          }}
        />
        <MoneyInput
          id={`${idPrefix}-amount`}
          label="Subsidy"
          value={draft.amount}
          error={problems.subsidy_amount}
          onChange={(amount) => {
            onDraftChange({ ...draft, amount });
          }}
        />
        <MoneyInput
          id={`${idPrefix}-payable`}
          label="Farmer payable"
          optional
          placeholder="Material less subsidy"
          description={
            derived === null
              ? "Empty: the material less the subsidy."
              : `Empty: material less subsidy, ${formatInr(derived.toFixed(2), { paise: true })}.`
          }
          value={draft.payable}
          error={problems.farmer_payable}
          onChange={(payable) => {
            onDraftChange({ ...draft, payable });
          }}
        />
      </div>
    </div>
  );
}

function MoneyInput({
  id,
  label,
  optional = false,
  placeholder,
  description,
  value,
  error,
  onChange,
}: {
  id: string;
  label: string;
  optional?: boolean;
  placeholder?: string;
  description?: string;
  value: string;
  error: string | undefined;
  onChange: (next: string) => void;
}): React.JSX.Element {
  const describedBy = error !== undefined ? `${id}-error` : description ? `${id}-hint` : undefined;
  return (
    <Field data-invalid={error === undefined ? undefined : true}>
      <FieldLabel htmlFor={id}>
        {label}
        {optional ? <span className="font-normal text-muted-foreground">(optional)</span> : null}
      </FieldLabel>
      <InputGroup>
        <InputGroupAddon>₹</InputGroupAddon>
        <InputGroupInput
          id={id}
          inputMode="decimal"
          autoComplete="off"
          className="tabular-nums"
          placeholder={placeholder}
          value={value}
          aria-invalid={error === undefined ? undefined : true}
          aria-describedby={describedBy}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      </InputGroup>
      {description !== undefined && error === undefined ? (
        <FieldDescription id={`${id}-hint`}>{description}</FieldDescription>
      ) : null}
      <FieldError id={`${id}-error`}>{error}</FieldError>
    </Field>
  );
}
