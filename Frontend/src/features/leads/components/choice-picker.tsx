"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxStatus,
} from "@/components/ui/combobox";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { partnerSearchQueryOptions } from "@/features/leads/api/leads.queries";
import { partnerTypeLabel } from "@/features/leads/lib/lead-labels";
import { useDebouncedValue } from "@/hooks/use-debounced-value";

/** Search once typing pauses for this long. */
const SEARCH_DEBOUNCE_MS = 250;

/** A picker's choice: a person or partner, or explicitly nobody. */
export interface Choice {
  /** "" for nobody. */
  readonly id: string;
  readonly name: string;
  readonly detail: string | null;
}

export const NO_PARTNER: Choice = { id: "", name: "No channel partner", detail: null };

export function sameChoice(a: Choice, b: Choice): boolean {
  return a.id === b.id;
}

/**
 * The text the field holds for a choice. "Nobody" holds none, so its name shows as the
 * placeholder and typing starts a fresh search: it used to search `q=No channel partnerBhavesh`
 * (walk F-9).
 */
function choiceInputText(choice: Choice): string {
  return choice.id === "" ? "" : choice.name;
}

/** Filters the list as you type, by name; "nobody" stays on offer whatever is typed. */
function matchesChoice(choice: Choice, query: string): boolean {
  const term = query.trim().toLowerCase();
  return choice.id === "" || term === "" || choice.name.toLowerCase().includes(term);
}

/** What the partner search is doing: failed, searching, or nothing to say. */
function searchStatus(failed: boolean, waiting: boolean): React.ReactNode {
  if (failed) {
    return "Partners couldn't be loaded. Check your connection, then type again.";
  }
  if (waiting) {
    return (
      <>
        <Spinner />
        Searching…
      </>
    );
  }
  return null;
}

/**
 * LEAD-008, SO-012 · A dealer or distributor the user may see, searched on the server by name,
 * code or contact person, with "No channel partner" first.
 */
export function PartnerSearchField({
  id,
  label = "Channel partner",
  description,
  value,
  error,
  onChange,
  className,
}: {
  id: string;
  label?: string;
  description: string;
  className?: string;
  value: Choice;
  error: string | null;
  onChange: (choice: Choice) => void;
}): React.JSX.Element {
  const [search, setSearch] = useState("");
  const term = useDebouncedValue(search.trim(), SEARCH_DEBOUNCE_MS);
  const query = useQuery(partnerSearchQueryOptions(term));
  const results: Choice[] = (query.data ?? []).map((partner) => ({
    id: partner.id,
    name: partner.name,
    detail: [partnerTypeLabel(partner.partnerType), partner.territoryName]
      .filter((part) => part !== null)
      .join(" · "),
  }));
  // Keep the chosen partner among the items so the field can name it during a search.
  const withChosen =
    value.id !== "" && !results.some((result) => result.id === value.id)
      ? [value, ...results]
      : results;
  const waiting = search.trim() !== term || query.isFetching;

  return (
    <Field data-invalid={error === null ? undefined : true} className={className}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <ChoicePicker
        id={id}
        items={[NO_PARTNER, ...withChosen]}
        value={value}
        onChange={onChange}
        onSearch={setSearch}
        placeholder={value.id === "" ? value.name : "Dealer name, code or contact person"}
        invalid={error !== null}
        describedBy={error === null ? `${id}-description` : `${id}-error`}
        emptyText={term === "" ? "No partners in your area." : `No partner matches “${term}”.`}
        status={searchStatus(query.isError, waiting)}
      />
      {error === null ? (
        <FieldDescription id={`${id}-description`}>{description}</FieldDescription>
      ) : null}
      <FieldError id={`${id}-error`}>{error ?? undefined}</FieldError>
    </Field>
  );
}

/**
 * A searchable single choice. Without `onSearch` it filters its items as you type; with it,
 * the caller searches the server and passes the results in.
 */
export function ChoicePicker({
  id,
  items,
  value,
  onChange,
  onSearch,
  placeholder,
  disabled = false,
  invalid,
  describedBy,
  emptyText,
  status = null,
}: {
  id: string;
  items: readonly Choice[];
  value: Choice;
  onChange: (choice: Choice) => void;
  onSearch?: (term: string) => void;
  placeholder: string;
  disabled?: boolean;
  invalid: boolean;
  describedBy: string;
  emptyText: string;
  status?: React.ReactNode;
}): React.JSX.Element {
  return (
    <Combobox
      items={items}
      value={value}
      onValueChange={(next: Choice | null) => {
        if (next !== null) {
          onChange(next);
        }
      }}
      onInputValueChange={(next, details) => {
        if (details.reason !== "item-press") {
          onSearch?.(next);
        }
      }}
      itemToStringLabel={choiceInputText}
      isItemEqualToValue={sameChoice}
      filter={onSearch === undefined ? matchesChoice : null}
      disabled={disabled}
    >
      <ComboboxInput
        id={id}
        placeholder={placeholder}
        autoComplete="off"
        aria-invalid={invalid ? true : undefined}
        aria-describedby={describedBy}
      />
      <ComboboxContent aria-busy={status === null ? undefined : true}>
        {status === null ? null : <ComboboxStatus>{status}</ComboboxStatus>}
        <ComboboxEmpty>{emptyText}</ComboboxEmpty>
        <ComboboxList>
          {(choice: Choice) => (
            <ComboboxItem key={choice.id === "" ? "none" : choice.id} value={choice}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{choice.name}</span>
                {choice.detail === null ? null : (
                  <span className="truncate text-xs text-muted-foreground">{choice.detail}</span>
                )}
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
