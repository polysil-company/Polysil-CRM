"use client";

import { UserSwitchIcon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

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
import { useAssignLead } from "@/features/leads/api/leads.mutations";
import { leadAssigneesQueryOptions } from "@/features/leads/api/leads.queries";
import type { AssignLeadRequest, Lead } from "@/features/leads/api/leads.schemas";
import { partnerTypeLabel } from "@/features/leads/lib/lead-labels";
import { stageChangeError } from "@/features/leads/lib/lead-lifecycle";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

import {
  type Choice,
  ChoicePicker,
  NO_PARTNER,
  PartnerSearchField,
  sameChoice,
} from "./choice-picker";

const log = createLogger({
  file: "features/leads/components/lead-assign-dialog.tsx",
  dataId: "LEAD-008",
});

const NO_OWNER: Choice = { id: "", name: "Unassigned", detail: "Back to the office's list" };
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
  const closeSoon = useCloseAfterSuccess(onClose);

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
      closeSoon();
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
          <PartnerSearchField
            id="assign-partner"
            description="The dealer or distributor who handles this lead."
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
          placeholder={
            query.isPending ? "Loading people…" : value.id === "" ? value.name : "Search a person"
          }
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
