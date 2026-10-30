"use client";

import { Cancel01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxStatus,
} from "@/components/ui/combobox";
import { Icon } from "@/components/ui/icon";
import { Spinner } from "@/components/ui/spinner";
import { leadListQueryOptions } from "@/features/leads/api/leads.queries";
import type { LeadStage } from "@/features/leads/api/leads.schemas";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** Search once typing pauses for this long. */
const SEARCH_DEBOUNCE_MS = 250;

/** FS-054 rule 3: 1 to 50 leads, each qualified or later. */
export const MAX_SUBSIDY_LEADS = 50;
const ORDERABLE_STAGES: readonly LeadStage[] = ["qualified", "quoted", "negotiation", "won"];

/** A lead on a subsidised order, as a form keeps it. A null code is a lead you can't see. */
export interface SubsidyLead {
  readonly id: string;
  readonly code: string | null;
  readonly name: string | null;
}

export interface SubsidyLeadsPickerProps {
  id: string;
  leads: readonly SubsidyLead[];
  onLeadsChange: (leads: SubsidyLead[]) => void;
  /** Once the order exists its first lead routes it and can't change (422 first_lead_fixed). */
  firstFixed?: boolean;
  invalid?: boolean;
  describedBy?: string;
}

/**
 * SO-008 · The leads a subsidised order covers (FS-054): picked by farmer, mobile or inquiry
 * number from the qualified ones and later, in order. The first is the order's lead.
 */
export function SubsidyLeadsPicker({
  id,
  leads,
  onLeadsChange,
  firstFixed = false,
  invalid = false,
  describedBy,
}: SubsidyLeadsPickerProps): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useQuery(
    leadListQueryOptions({
      cursor: null,
      pageSize: 8,
      sort: "createdAt",
      order: "desc",
      q: term,
      stage: ORDERABLE_STAGES,
      source: null,
      type: null,
      areas: [],
      campaign: null,
    }),
  );
  const chosen = new Set(leads.map((lead) => lead.id));
  const results: SubsidyLead[] = (query.data?.items ?? [])
    .filter((lead) => !chosen.has(lead.id))
    .map((lead) => ({ id: lead.id, code: lead.code, name: lead.customerName }));
  const waiting = search.trim() !== term || query.isFetching;
  const full = leads.length >= MAX_SUBSIDY_LEADS;

  return (
    <div className="flex flex-col gap-2">
      {leads.length === 0 ? null : (
        <ol aria-label="Leads on this order" className="flex flex-col gap-1">
          {leads.map((lead, index) => {
            const label = lead.code ?? "a lead you cannot see";
            const fixed = index === 0 && firstFixed;
            return (
              <li
                key={lead.id}
                className="flex min-h-11 items-center gap-2 rounded-md border border-border px-3 py-1 text-sm"
              >
                <span className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-2">
                  <span className="font-mono text-foreground">{label}</span>
                  {lead.name === null ? null : (
                    <span className="truncate text-muted-foreground">{lead.name}</span>
                  )}
                  {index === 0 ? (
                    <span className="text-xs text-muted-foreground">(the order&apos;s lead)</span>
                  ) : null}
                </span>
                {fixed ? null : (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-md"
                    aria-label={`Remove ${label}`}
                    onClick={() => {
                      onLeadsChange(leads.filter((item) => item.id !== lead.id));
                    }}
                  >
                    <Icon icon={Cancel01Icon} />
                  </Button>
                )}
              </li>
            );
          })}
        </ol>
      )}
      {full ? (
        <p className="text-sm text-muted-foreground">
          {MAX_SUBSIDY_LEADS} leads is the most one order covers.
        </p>
      ) : (
        <Combobox
          items={results}
          value={null}
          inputValue={search}
          onValueChange={(next: SubsidyLead | null) => {
            if (next !== null && !chosen.has(next.id)) {
              onLeadsChange([...leads, next]);
            }
            setSearch("");
          }}
          onInputValueChange={(next, details) => {
            if (details.reason !== "item-press") setSearch(next);
          }}
          itemToStringLabel={(lead: SubsidyLead) => lead.code ?? lead.id}
          isItemEqualToValue={(item: SubsidyLead, selected: SubsidyLead) => item.id === selected.id}
          filter={null}
        >
          <ComboboxInput
            id={id}
            placeholder={leads.length === 0 ? "Farmer, mobile or inquiry number" : "Add a lead"}
            autoComplete="off"
            aria-invalid={invalid || undefined}
            aria-describedby={describedBy}
          />
          <ComboboxContent aria-busy={waiting || undefined}>
            <ComboboxStatus>
              {query.isError ? (
                "Leads couldn't be loaded. Check your connection, then type again."
              ) : waiting ? (
                <>
                  <Spinner />
                  Searching…
                </>
              ) : null}
            </ComboboxStatus>
            <ComboboxEmpty>
              {waiting || query.isError
                ? null
                : term === ""
                  ? "No qualified leads to add."
                  : `No qualified lead matches “${term}”.`}
            </ComboboxEmpty>
            <ComboboxList>
              {(lead: SubsidyLead) => (
                <ComboboxItem key={lead.id} value={lead}>
                  <span className="flex min-w-0 flex-col">
                    <span className="truncate font-mono">{lead.code}</span>
                    {lead.name === null ? null : (
                      <span className="truncate text-xs text-muted-foreground">{lead.name}</span>
                    )}
                  </span>
                </ComboboxItem>
              )}
            </ComboboxList>
          </ComboboxContent>
        </Combobox>
      )}
    </div>
  );
}
