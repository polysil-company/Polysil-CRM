"use client";

import { UserSwitchIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

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
import { Spinner } from "@/components/ui/spinner";
import { useAssignLead } from "@/features/leads/api/leads.mutations";
import {
  leadAssigneesQueryOptions,
  partnerSearchQueryOptions,
} from "@/features/leads/api/leads.queries";
import type { AssignLeadRequest, Lead } from "@/features/leads/api/leads.schemas";
import { partnerTypeLabel } from "@/features/leads/lib/lead-labels";
import { stageChangeError } from "@/features/leads/lib/lead-lifecycle";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/leads/components/lead-assign-dialog.tsx",
  dataId: "LEAD-008",
});

/** Search once typing pauses for this long. */
const SEARCH_DEBOUNCE_MS = 250;
/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

/** A picker's choice: a person or partner, or explicitly nobody. */
interface Choice {
  /** "" for nobody. */
  readonly id: string;
  readonly name: string;
  readonly detail: string | null;
}

const NO_OWNER: Choice = { id: "", name: "Unassigned", detail: "Back to the office's list" };
const NO_PARTNER: Choice = { id: "", name: "No channel partner", detail: null };

function sameChoice(a: Choice, b: Choice): boolean {
  return a.id === b.id;
}

function ownerOf(lead: Lead): Choice {
  return lead.owner
    ? { id: lead.owner.id, name: lead.owner.name, detail: lead.ownerOrgUnit.name }
    : NO_OWNER;
}

function partnerOf(lead: Lead): Choice {
  return lead.channelPartner
    ? {
        id: lead.channelPartner.id,
        name: lead.channelPartner.name,
        detail: partnerTypeLabel(lead.channelPartner.partnerType),
      }
    : NO_PARTNER;
}

export interface LeadAssignDialogProps {
  lead: Lead;
}

/**
 * LEAD-008 · Change a lead's owner or channel partner. Only what changed is sent, so a
 * field left alone is never overwritten. Who may be made owner comes from the backend:
 * someone who may not set owners is told so rather than offered a list that would fail.
 * A closed lead (won, lost, merged) cannot be reassigned, so the button is not shown for it.
 */
export function LeadAssignDialog({ lead }: LeadAssignDialogProps): React.JSX.Element {
  const [open, setOpen] = useState(false);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Icon icon={UserSwitchIcon} />
        Assign
      </DialogTrigger>
      <DialogContent size="sm">
        {open ? (
          <AssignForm
            lead={lead}
            onClose={() => {
              setOpen(false);
            }}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function AssignForm({ lead, onClose }: { lead: Lead; onClose: () => void }): React.JSX.Element {
  const [owner, setOwner] = useState<Choice>(() => ownerOf(lead));
  const [partner, setPartner] = useState<Choice>(() => partnerOf(lead));
  const [ownerError, setOwnerError] = useState<string | null>(null);
  const [partnerError, setPartnerError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const assign = useAssignLead();
  const idempotency = useIdempotencyKey();
  const closeTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    return () => {
      window.clearTimeout(closeTimer.current);
    };
  }, []);

  const ownerChanged = !sameChoice(owner, ownerOf(lead));
  const partnerChanged = !sameChoice(partner, partnerOf(lead));

  const submit = useAsyncAction({
    action: (body: AssignLeadRequest) =>
      assign.mutateAsync({
        leadId: lead.id,
        body,
        idempotencyKey: idempotency.keyFor({ leadId: lead.id, ...body }),
      }),
    logger: log,
    fn: "handleAssign",
    dataId: "LEAD-008",
    onSuccess: (updated) => {
      toast.success("Lead assigned", {
        description: updated.owner
          ? `${updated.customerName} · owner ${updated.owner.name}`
          : `${updated.customerName} · unassigned`,
      });
      closeTimer.current = window.setTimeout(onClose, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields?.owner_user_id !== undefined || fields?.assigned_partner_id !== undefined) {
        if (fields.owner_user_id !== undefined) {
          setOwnerError("You can't make this person the owner");
        }
        if (fields.assigned_partner_id !== undefined) {
          setPartnerError("This partner isn't in your area");
        }
        return;
      }
      const refusal = stageChangeError(error);
      if (refusal.stale) {
        toast.error("The lead has changed", { description: refusal.message });
        onClose();
        return;
      }
      setFormError(refusal.message);
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        if (!ownerChanged && !partnerChanged) {
          return;
        }
        setOwnerError(null);
        setPartnerError(null);
        setFormError(null);
        void submit.run({
          ...(ownerChanged ? { owner_user_id: owner.id === "" ? null : owner.id } : {}),
          ...(partnerChanged ? { assigned_partner_id: partner.id === "" ? null : partner.id } : {}),
        });
      }}
    >
      <DialogHeader>
        <DialogTitle>Assign lead</DialogTitle>
        <DialogDescription>
          Who works on {lead.customerName}, and through which partner.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="gap-4">
          <OwnerField
            value={owner}
            officeName={lead.ownerOrgUnit.name}
            error={ownerError}
            onChange={(next) => {
              setOwner(next);
              setOwnerError(null);
            }}
          />
          <PartnerField
            value={partner}
            error={partnerError}
            onChange={(next) => {
              setPartner(next);
              setPartnerError(null);
            }}
          />
        </FieldGroup>
        {formError === null ? null : (
          <p
            role="alert"
            className="mt-4 rounded-md border border-border bg-danger-soft p-3 text-sm text-danger"
          >
            {formError}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
          disabled={!ownerChanged && !partnerChanged && submit.state === "idle"}
        >
          Save
        </Button>
      </DialogFooter>
    </form>
  );
}

function OwnerField({
  value,
  officeName,
  error,
  onChange,
}: {
  value: Choice;
  officeName: string;
  error: string | null;
  onChange: (choice: Choice) => void;
}): React.JSX.Element {
  const query = useQuery(leadAssigneesQueryOptions());
  const people: Choice[] = (query.data ?? []).map((person) => ({
    id: person.id,
    name: person.name,
    detail: person.officeName,
  }));
  const cannotAssign = query.isSuccess && people.length === 0;

  return (
    <Field data-invalid={error === null ? undefined : true}>
      <FieldLabel htmlFor="assign-owner">Owner</FieldLabel>
      {cannotAssign ? (
        <p id="assign-owner" className="text-sm text-muted-foreground">
          {value.name}. Only a manager can change the owner.
        </p>
      ) : (
        <ChoicePicker
          id="assign-owner"
          items={[NO_OWNER, ...people.filter((person) => person.id !== "")]}
          value={value}
          onChange={onChange}
          placeholder={query.isPending ? "Loading people…" : "Search a person"}
          disabled={query.isPending || query.isError}
          invalid={error !== null}
          describedBy={error === null ? "assign-owner-description" : "assign-owner-error"}
          emptyText="No one by that name."
        />
      )}
      {query.isError ? (
        <p role="alert" className="flex items-center gap-2 text-xs text-danger">
          The people you can assign couldn&apos;t be loaded.
          <Button
            type="button"
            variant="link"
            size="xs"
            onClick={() => {
              void query.refetch();
            }}
          >
            Try again
          </Button>
        </p>
      ) : null}
      {error === null && !cannotAssign ? (
        <FieldDescription id="assign-owner-description">
          Unassigned leads wait in {officeName}&apos;s list.
        </FieldDescription>
      ) : null}
      <FieldError id="assign-owner-error">{error ?? undefined}</FieldError>
    </Field>
  );
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

function PartnerField({
  value,
  error,
  onChange,
}: {
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
    <Field data-invalid={error === null ? undefined : true}>
      <FieldLabel htmlFor="assign-partner">Channel partner</FieldLabel>
      <ChoicePicker
        id="assign-partner"
        items={[NO_PARTNER, ...withChosen]}
        value={value}
        onChange={onChange}
        onSearch={setSearch}
        placeholder="Search a dealer or distributor"
        invalid={error !== null}
        describedBy={error === null ? "assign-partner-description" : "assign-partner-error"}
        emptyText={term === "" ? "No partners in your area." : `No partner matches “${term}”.`}
        status={searchStatus(query.isError, waiting)}
      />
      {error === null ? (
        <FieldDescription id="assign-partner-description">
          The dealer or distributor who handles this lead.
        </FieldDescription>
      ) : null}
      <FieldError id="assign-partner-error">{error ?? undefined}</FieldError>
    </Field>
  );
}

/**
 * A searchable single choice. Without `onSearch` it filters its items as you type; with it,
 * the caller searches the server and passes the results in.
 */
function ChoicePicker({
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
      itemToStringLabel={(choice: Choice) => choice.name}
      isItemEqualToValue={sameChoice}
      {...(onSearch === undefined ? {} : { filter: null })}
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
