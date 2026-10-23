"use client";

import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldDescription, FieldLegend, FieldSet } from "@/components/ui/field";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { quotationListQueryOptions } from "@/features/quotations/api/quotations.queries";
import type {
  Quotation,
  QuotationListParams,
  QuotationSummary,
} from "@/features/quotations/api/quotations.schemas";
import { quotationTitle } from "@/features/quotations/lib/quotation-labels";
import { formatInr, sumRupees } from "@/lib/format";

/** The backend's largest page: a dealer rarely holds more accepted quotations at once. */
const CANDIDATE_PAGE = 100;

function candidateParams(partnerId: string): QuotationListParams {
  return {
    cursor: null,
    pageSize: CANDIDATE_PAGE,
    q: "",
    status: ["accepted"],
    salesType: null,
    currentOnly: true,
    leadId: null,
    partnerId,
    // BE-029 · only the ones on no live order; a 409 still marks one an unseen order holds
    orderable: true,
    countTotal: false,
  };
}

/**
 * Whether a quotation can join this one on an order. A subsidised order comes from exactly one
 * quotation, and an export order only from export quotations (both refused as `type_mismatch`).
 */
function joins(base: Quotation, other: QuotationSummary): boolean {
  if (other.id === base.id || other.supersededBy !== null) return false;
  if (other.salesType === "subsidised") return false;
  return (other.salesType === "export") === (base.salesType === "export");
}

/** SO-011 · Whether this quotation may gather others: a dealer's, and not subsidised. */
export function canConsolidate(quotation: Quotation): boolean {
  return quotation.partner !== null && quotation.salesType !== "subsidised";
}

export interface ConsolidateQuotationsProps {
  quotation: Quotation;
  /** The other quotations ticked, in the order they were ticked. */
  selected: readonly string[];
  onSelectedChange: (next: string[]) => void;
  /** Quotations the backend said are on an order already: shown, and can't be ticked. */
  onOrder: readonly string[];
  disabled?: boolean;
}

/**
 * SO-011 · The dealer's other accepted, current quotations, to make one consolidated order. The
 * backend checks that they agree on partner, place of supply, seller, price date, office and
 * territory, and names the field when they don't.
 */
export function ConsolidateQuotations({
  quotation,
  selected,
  onSelectedChange,
  onOrder,
  disabled = false,
}: ConsolidateQuotationsProps): React.JSX.Element | null {
  const partner = quotation.partner;
  const query = useQuery({
    ...quotationListQueryOptions(candidateParams(partner?.id ?? "")),
    enabled: partner !== null,
  });
  if (partner === null) return null;

  const candidates = (query.data?.items ?? []).filter((other) => joins(quotation, other));
  const chosen = candidates.filter((other) => selected.includes(other.id));
  const total = sumRupees([quotation.totals.total, ...chosen.map((other) => other.totals.total)]);
  const leads = new Set(
    [quotation.lead?.id, ...chosen.map((other) => other.lead?.id)].filter((id) => id !== undefined),
  );

  return (
    <FieldSet>
      <FieldLegend>
        Add {partner.name}&apos;s other accepted quotations{" "}
        <span className="font-normal text-muted-foreground">(optional)</span>
      </FieldLegend>
      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading the dealer's quotations" className="space-y-2">
          <Skeleton className="h-10 w-full rounded-lg" />
          <Skeleton className="h-10 w-full rounded-lg" />
        </div>
      ) : query.status === "error" ? (
        <FieldDescription>
          The dealer&apos;s other quotations couldn&apos;t be loaded. This one can still be ordered
          on its own.
        </FieldDescription>
      ) : candidates.length === 0 ? (
        <FieldDescription>No other accepted quotation of this dealer is waiting.</FieldDescription>
      ) : (
        <>
          <ul aria-label="Other accepted quotations" className="flex flex-col gap-1">
            {candidates.map((other) => {
              const taken = onOrder.includes(other.id);
              const id = `consolidate-${other.id}`;
              return (
                <li key={other.id}>
                  <Field
                    orientation="horizontal"
                    className="items-start rounded-lg p-2 hover:bg-muted/50"
                  >
                    <Checkbox
                      id={id}
                      checked={selected.includes(other.id)}
                      disabled={disabled || taken}
                      onCheckedChange={(checked) => {
                        onSelectedChange(
                          checked
                            ? [...selected, other.id]
                            : selected.filter((value) => value !== other.id),
                        );
                      }}
                    />
                    <Label
                      htmlFor={id}
                      className="flex min-w-0 flex-1 flex-col items-start gap-0.5 font-normal"
                    >
                      <span className="flex w-full flex-wrap items-baseline justify-between gap-x-3">
                        <span className="font-medium text-foreground">{quotationTitle(other)}</span>
                        <span className="text-foreground tabular-nums">
                          {formatInr(other.totals.total, { paise: true })}
                        </span>
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {other.partyName}
                        {other.lead === null ? "" : ` · ${other.lead.code}`}
                        {taken ? " · already on an order" : ""}
                      </span>
                    </Label>
                  </Field>
                </li>
              );
            })}
          </ul>
          <FieldDescription aria-live="polite">
            {chosen.length === 0
              ? "Tick any to make one order of them all."
              : `${String(chosen.length + 1)} quotations, ${formatInr(total, { paise: true })} together.${
                  leads.size > 1
                    ? ` They are on ${String(leads.size)} leads, so the order is consolidated: ${partner.name} is the party and it has no single lead.`
                    : ""
                }`}
          </FieldDescription>
        </>
      )}
    </FieldSet>
  );
}
