"use client";

import type * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import type { CommissionStatus } from "@/features/commission/api/commission.schemas";
import {
  COMMISSION_STATUS_BADGE,
  COMMISSION_STATUS_LABELS,
  formatPct,
} from "@/features/commission/lib/commission-labels";
import { formatInr } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Rupees as typed: whole or with paise. Empty is allowed where the field is optional. */
export function moneyProblem(value: string, required: boolean): string | null {
  const trimmed = value.trim();
  if (trimmed === "") return required ? "Enter rupees, or 0." : null;
  return /^\d+(\.\d{1,2})?$/.test(trimmed) ? null : "Enter rupees, like 12000 or 12000.50.";
}

export function CommissionStatusBadge({ status }: { status: CommissionStatus }): React.JSX.Element {
  return (
    <Badge variant={COMMISSION_STATUS_BADGE[status]} dot>
      {COMMISSION_STATUS_LABELS[status]}
    </Badge>
  );
}

export function MoneyField({
  id,
  label,
  optional = false,
  placeholder,
  description,
  value,
  error,
  disabled = false,
  onChange,
}: {
  id: string;
  label: string;
  optional?: boolean;
  placeholder?: string;
  description?: string;
  value: string;
  error: string | null;
  disabled?: boolean;
  onChange: (next: string) => void;
}): React.JSX.Element {
  const describedBy =
    error !== null ? `${id}-error` : description === undefined ? undefined : `${id}-hint`;
  return (
    <Field data-invalid={error === null ? undefined : true}>
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
          disabled={disabled}
          aria-invalid={error === null ? undefined : true}
          aria-describedby={describedBy}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      </InputGroup>
      {error === null ? (
        description === undefined ? null : (
          <FieldDescription id={`${id}-hint`}>{description}</FieldDescription>
        )
      ) : (
        <FieldError id={`${id}-error`}>{error}</FieldError>
      )}
    </Field>
  );
}

export interface FigureRows {
  readonly costExclGst: string;
  readonly giFitting: string;
  readonly pvcHdpeFitting: string;
  readonly installation: string;
  readonly commissionBase: string;
  readonly commissionPct: string;
  readonly commissionAmount: string;
  readonly todBase: string;
  readonly todPct: string;
  readonly todAmount: string;
  readonly total: string;
}

/**
 * Stage 18's working, line by line: the cost before GST, less the fittings and installation,
 * is the commission base; each amount is its base at its rate; the total is both.
 */
export function CommissionFigures({
  figures,
  label,
  className,
}: {
  figures: FigureRows;
  label: string;
  className?: string;
}): React.JSX.Element {
  const money = (value: string): string => formatInr(value, { paise: true });
  const less = (value: string): string => `−${money(value)}`;
  const rows: readonly { term: string; value: string; strong?: boolean; rule?: boolean }[] = [
    { term: "Cost before GST", value: money(figures.costExclGst) },
    { term: "GI fittings", value: less(figures.giFitting) },
    { term: "PVC and HDPE fittings", value: less(figures.pvcHdpeFitting) },
    { term: "Installation", value: less(figures.installation) },
    { term: "Commission base", value: money(figures.commissionBase), rule: true },
    {
      term: `Commission at ${formatPct(figures.commissionPct)}`,
      value: money(figures.commissionAmount),
    },
    {
      term: `TOD at ${formatPct(figures.todPct)} of ${money(figures.todBase)}`,
      value: money(figures.todAmount),
    },
    { term: "Total to the dealer", value: money(figures.total), strong: true, rule: true },
  ];
  return (
    <dl aria-label={label} className={cn("grid grid-cols-2 gap-x-4 gap-y-1.5 text-sm", className)}>
      {rows.map((row) => (
        <div
          key={row.term}
          className={cn(
            "col-span-2 grid grid-cols-subgrid",
            row.rule && "border-t border-border pt-1.5",
          )}
        >
          <dt className={row.strong ? "font-semibold text-foreground" : "text-muted-foreground"}>
            {row.term}
          </dt>
          <dd
            className={cn(
              "text-right tabular-nums",
              row.strong ? "text-base font-semibold text-foreground" : "text-foreground",
            )}
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
