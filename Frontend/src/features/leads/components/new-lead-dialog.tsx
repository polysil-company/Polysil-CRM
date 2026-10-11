"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Add01Icon } from "@hugeicons/core-free-icons";
import { parseAsBoolean, useQueryState } from "nuqs";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { useForm, type DefaultValues } from "react-hook-form";
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
import { useCreateLead } from "@/features/leads/api/leads.mutations";
import {
  createLeadFormSchema,
  type CreateLeadFormValues,
  type CreateLeadRequest,
} from "@/features/leads/api/leads.schemas";
import { createLeadFieldErrors } from "@/features/leads/lib/create-lead-errors";
import { describeCreatedLead } from "@/features/leads/lib/lead-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { toUserFacingError } from "@/lib/api/error-messages";
import { createRequestId } from "@/lib/api/request-id";
import { createLogger } from "@/lib/logger";

import { LeadFields } from "./lead-fields";

const log = createLogger({
  file: "features/leads/components/new-lead-dialog.tsx",
  dataId: "LEAD-002",
});

const EMPTY_FORM: DefaultValues<CreateLeadFormValues> = {
  customerName: "",
  phone: "",
  email: "",
  territory: null,
  village: "",
  source: null,
  estimatedValue: "",
  crops: [],
  landAcres: "",
  note: "",
};

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 700;

/**
 * LEAD-002 · New lead. Open state lives in the URL (?newLead=true), so the command menu and
 * links can open it. Validation runs on blur, then on change; server field errors (422) land
 * on the matching field; anything else shows an inline error with a copyable reference.
 *
 * Retrying the same details reuses the Idempotency-Key, so a save whose reply was lost is
 * replayed by the backend instead of creating the lead twice. Changing any detail makes a
 * new key. Duplicates are never refused: the backend flags them, and the toast says so.
 */
export function NewLeadDialog(): React.JSX.Element {
  const [open, setOpen] = useQueryState("newLead", parseAsBoolean.withDefault(false));
  const [formError, setFormError] = useState<unknown>(null);
  const lastAttempt = useRef<{ body: string; key: string } | null>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const createLead = useCreateLead();
  const form = useForm<CreateLeadFormValues, unknown, CreateLeadRequest>({
    resolver: zodResolver(createLeadFormSchema),
    defaultValues: EMPTY_FORM,
    mode: "onTouched",
  });

  // The dialog can be left before the success check has had its moment; the timer must not
  // outlive it, or it resets a form that is gone and writes to another page's URL.
  useEffect(() => {
    return () => {
      window.clearTimeout(closeTimer.current);
    };
  }, []);

  const idempotencyKeyFor = (body: CreateLeadRequest): string => {
    const serialized = JSON.stringify(body);
    if (lastAttempt.current?.body !== serialized) {
      lastAttempt.current = { body: serialized, key: createRequestId() };
    }
    return lastAttempt.current.key;
  };

  const applyServerFieldErrors = (error: unknown): boolean => {
    const fieldErrors = createLeadFieldErrors(error);
    fieldErrors.forEach(({ field, message }, index) => {
      form.setError(field, { type: "server", message }, { shouldFocus: index === 0 });
    });
    return fieldErrors.length > 0;
  };

  const resetForm = (): void => {
    window.clearTimeout(closeTimer.current);
    form.reset(EMPTY_FORM);
    lastAttempt.current = null;
  };

  const submit = useAsyncAction({
    action: (body: CreateLeadRequest) =>
      createLead.mutateAsync({ body, idempotencyKey: idempotencyKeyFor(body) }),
    logger: log,
    fn: "handleCreateLead",
    dataId: "LEAD-002",
    onSuccess: (lead) => {
      toast.success("Lead created", { description: describeCreatedLead(lead) });
      closeTimer.current = window.setTimeout(() => {
        void setOpen(false);
        resetForm();
      }, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      if (!applyServerFieldErrors(error)) {
        setFormError(error);
      }
    },
  });

  const handleOpenChange = (next: boolean): void => {
    if (submit.isBusy) {
      return; // Never close in the middle of a save.
    }
    if (!next) {
      resetForm();
      setFormError(null);
      submit.reset();
    }
    void setOpen(next);
  };

  const onValid = (body: CreateLeadRequest): void => {
    setFormError(null);
    void submit.run(body);
  };

  const formErrorView = formError === null ? null : toUserFacingError(formError);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button />}>
        <Icon icon={Add01Icon} />
        New lead
      </DialogTrigger>
      <DialogContent>
        <form
          noValidate
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            void form.handleSubmit(onValid)(event);
          }}
        >
          <DialogHeader>
            <DialogTitle>New lead</DialogTitle>
            <DialogDescription>
              Capture the enquiry now. Quotations can be added later.
            </DialogDescription>
          </DialogHeader>

          <DialogBody>
            <LeadFields form={form} idPrefix="lead" withNote />

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
            <DialogClose
              render={<Button type="button" variant="outline" disabled={submit.isBusy} />}
            >
              Cancel
            </DialogClose>
            <Button
              type="submit"
              state={submit.state}
              loadingLabel="Creating…"
              successLabel="Created"
              errorLabel="Not saved"
            >
              Create lead
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
