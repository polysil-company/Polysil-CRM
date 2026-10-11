"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Delete02Icon, Edit02Icon } from "@hugeicons/core-free-icons";
import { useRouter } from "next/navigation";
import { useState } from "react";
import type * as React from "react";
import { useForm } from "react-hook-form";
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
import { Icon } from "@/components/ui/icon";
import { useDeleteLead, usePatchLead } from "@/features/leads/api/leads.mutations";
import {
  createLeadFormSchema,
  type CreateLeadFormValues,
  type CreateLeadRequest,
  type Lead,
  type PatchLeadRequest,
} from "@/features/leads/api/leads.schemas";
import { createLeadFieldErrors } from "@/features/leads/lib/create-lead-errors";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatIndianPhone } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { LeadFields } from "./lead-fields";

const log = createLogger({
  file: "features/leads/components/lead-edit-dialog.tsx",
  dataId: "LEAD-010",
});

/** The fields a patch may carry, in the order the form shows them. */
const PATCH_KEYS = [
  "farmer_name",
  "mobile",
  "email",
  "territory_id",
  "village",
  "inquiry_type",
  "mis_system",
  "source",
  "estimated_value",
  "crops",
  "land_acres",
] as const satisfies readonly (keyof PatchLeadRequest)[];

function formValuesOf(lead: Lead): CreateLeadFormValues {
  return {
    customerName: lead.customerName,
    phone: formatIndianPhone(lead.phone),
    email: lead.email ?? "",
    territory: { id: lead.territory.id, name: lead.territory.name, level: lead.territory.level },
    village: lead.village ?? "",
    type: lead.type,
    misSystem: lead.misSystem,
    source: lead.source,
    estimatedValue: lead.estimatedValue === null ? "" : String(Number(lead.estimatedValue)),
    crops: lead.crops.map((crop) => crop.code),
    landAcres: lead.landAcres === null ? "" : String(Number(lead.landAcres)),
    note: "",
  };
}

/** Only the fields that differ from the lead as loaded; the backend leaves the rest. */
function patchOf(before: CreateLeadRequest | null, after: CreateLeadRequest): PatchLeadRequest {
  const patch: Record<string, unknown> = {};
  for (const key of PATCH_KEYS) {
    if (before === null || JSON.stringify(before[key]) !== JSON.stringify(after[key])) {
      patch[key] = after[key];
    }
  }
  return patch;
}

/**
 * LEAD-010 · Correct a lead's own fields: who, where, what they want and how big. Only what
 * changed is sent; the stage, owner and partner have their own actions. A closed lead can't be
 * edited (`stage_terminal`), and a refused field is named on the form.
 */
export function LeadEditDialog({ lead }: { lead: Lead }): React.JSX.Element {
  const [open, setOpen] = useState(false);
  const [formError, setFormError] = useState<unknown>(null);
  const [initial] = useState(() => formValuesOf(lead));
  const patch = usePatchLead();
  const idempotency = useIdempotencyKey();
  const form = useForm<CreateLeadFormValues, unknown, CreateLeadRequest>({
    resolver: zodResolver(createLeadFormSchema),
    defaultValues: initial,
    mode: "onTouched",
  });

  const save = useAsyncAction({
    action: (values: CreateLeadRequest) => {
      const parsed = createLeadFormSchema.safeParse(initial);
      const body = patchOf(parsed.success ? parsed.data : null, values);
      return patch.mutateAsync({
        leadId: lead.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: lead.id, ...body }),
      });
    },
    logger: log,
    fn: "handleEditLead",
    dataId: "LEAD-010",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success("Lead updated", { description: `${saved.customerName} · ${saved.code}` });
      setOpen(false);
    },
    onError: (error) => {
      const fields = createLeadFieldErrors(error);
      fields.forEach(({ field, message }, index) => {
        form.setError(field, { type: "server", message }, { shouldFocus: index === 0 });
      });
      if (fields.length === 0) setFormError(error);
    },
  });

  const formErrorView =
    formError === null
      ? null
      : isApiError(formError) && formError.code === "stage_terminal"
        ? {
            title: "This lead is closed",
            description: "A won, lost or merged lead can't be edited. Reopen it first.",
            reference: undefined,
          }
        : toUserFacingError(formError);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (save.isBusy) return;
        if (next) {
          form.reset(formValuesOf(lead));
          setFormError(null);
          save.reset();
        }
        setOpen(next);
      }}
    >
      <DialogTrigger render={<Button variant="outline" size="sm" />}>
        <Icon icon={Edit02Icon} />
        Edit
      </DialogTrigger>
      <DialogContent>
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            setFormError(null);
            void form.handleSubmit((values) => save.run(values))(event);
          }}
        >
          <DialogHeader>
            <DialogTitle>Edit {lead.customerName}</DialogTitle>
            <DialogDescription>
              Correct the lead&apos;s details. Its stage, owner and dealer change from their own
              buttons.
            </DialogDescription>
          </DialogHeader>
          <DialogBody>
            <LeadFields form={form} idPrefix="edit-lead" />
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
            <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
              Cancel
            </DialogClose>
            <Button
              type="submit"
              state={save.state}
              loadingLabel="Saving…"
              successLabel="Saved"
              errorLabel="Not saved"
            >
              Save changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * LEAD-011 · Delete a lead, for holders of `leads.delete`. It disappears for everyone else, and
 * its pending duplicate pairs close. Asks first; then goes back to the list.
 */
export function LeadDeleteDialog({ lead }: { lead: Lead }): React.JSX.Element {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const remove = useDeleteLead();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<{ title: string; description: string } | null>(null);
  const run = useAsyncAction({
    action: () =>
      remove.mutateAsync({ leadId: lead.id, idempotencyKey: idempotency.keyFor({ id: lead.id }) }),
    logger: log,
    fn: "handleDeleteLead",
    dataId: "LEAD-011",
    onSuccess: () => {
      toast.success("Lead deleted", { description: `${lead.customerName} · ${lead.code}` });
      router.push("/leads");
    },
    onError: (error) => {
      const view = toUserFacingError(error);
      setRefusal({ title: view.title, description: view.description });
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (run.isBusy) return;
        if (next) setRefusal(null);
        setOpen(next);
      }}
    >
      <DialogTrigger render={<Button variant="ghost" />}>
        <Icon icon={Delete02Icon} />
        Delete
      </DialogTrigger>
      <DialogContent size="sm">
        <DialogHeader>
          <DialogTitle>Delete {lead.customerName}?</DialogTitle>
          <DialogDescription>
            {lead.code} disappears from every list. Its quotations and orders stay as they are.
          </DialogDescription>
        </DialogHeader>
        <DialogBody>
          {refusal === null ? null : (
            <div
              role="alert"
              className="flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
            >
              <p className="font-medium text-danger">{refusal.title}</p>
              <p className="text-muted-foreground">{refusal.description}</p>
            </div>
          )}
        </DialogBody>
        <DialogFooter>
          <DialogClose render={<Button type="button" variant="outline" disabled={run.isBusy} />}>
            Keep it
          </DialogClose>
          <Button
            variant="destructive"
            state={run.state}
            loadingLabel="Deleting…"
            successLabel="Deleted"
            errorLabel="Not deleted"
            onClick={() => {
              setRefusal(null);
              void run.run();
            }}
          >
            Delete lead
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
