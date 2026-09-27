"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState } from "react-hook-form";
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
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { useReopenLead, useTransitionLead } from "@/features/leads/api/leads.mutations";
import {
  LEAD_STAGE_NOTE_MAX_LENGTH,
  markLostFormSchema,
  type Lead,
  type MarkLostFormValues,
} from "@/features/leads/api/leads.schemas";
import { LEAD_STAGE_LABELS } from "@/features/leads/lib/lead-labels";
import { stageChangeError } from "@/features/leads/lib/lead-lifecycle";
import { lookupListQueryOptions } from "@/features/lookups/api/lookups.queries";
import { LookupSelect } from "@/features/lookups/components/lookup-select";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/leads/components/lead-stage-dialog.tsx",
  dataId: "LEAD-007",
});

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

/** The stage changes that ask before acting: they close or reopen the lead. */
export type StageDialogKind = "won" | "lost" | "reopen";

export interface LeadStageDialogProps {
  lead: Lead;
  /** Which dialog is open; null when none. */
  kind: StageDialogKind | null;
  onClose: () => void;
}

/**
 * LEAD-007 · Confirms a stage change that closes or reopens a lead. Mark as lost needs a
 * reason from the admin list; a note is optional on lost and on reopen. A refusal because
 * the lead moved elsewhere closes the dialog and says so — the page then shows the latest.
 */
export function LeadStageDialog({ lead, kind, onClose }: LeadStageDialogProps): React.JSX.Element {
  return (
    <Dialog
      open={kind !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent size="sm">
        {kind === "lost" ? <MarkLostForm lead={lead} onClose={onClose} /> : null}
        {kind === "won" ? <MarkWonForm lead={lead} onClose={onClose} /> : null}
        {kind === "reopen" ? <ReopenForm lead={lead} onClose={onClose} /> : null}
      </DialogContent>
    </Dialog>
  );
}

interface FormProps {
  lead: Lead;
  onClose: () => void;
}

/** Closes the dialog a moment after success, and never after the dialog is gone. */
function useCloseAfterSuccess(onClose: () => void): () => void {
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    return () => {
      window.clearTimeout(timer.current);
    };
  }, []);
  return () => {
    timer.current = window.setTimeout(onClose, CLOSE_AFTER_SUCCESS_MS);
  };
}

/** A refusal: stale ones close the dialog with a toast, the rest show inside it. */
function useRefusal(onClose: () => void): {
  message: string | null;
  handle: (error: unknown) => void;
  clear: () => void;
} {
  const [message, setMessage] = useState<string | null>(null);
  return {
    message,
    handle: (error) => {
      const refusal = stageChangeError(error);
      if (refusal.stale) {
        toast.error("The lead has changed", { description: refusal.message });
        onClose();
        return;
      }
      setMessage(refusal.message);
    },
    clear: () => {
      setMessage(null);
    },
  };
}

function RefusalAlert({ message }: { message: string | null }): React.JSX.Element | null {
  if (message === null) {
    return null;
  }
  return (
    <p
      role="alert"
      className="mt-4 rounded-md border border-border bg-danger-soft p-3 text-sm text-danger"
    >
      {message}
    </p>
  );
}

function MarkLostForm({ lead, onClose }: FormProps): React.JSX.Element {
  const transition = useTransitionLead();
  const idempotency = useIdempotencyKey();
  const refusal = useRefusal(onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const { data: reasons } = useQuery(lookupListQueryOptions("lost-reasons"));
  const form = useForm<MarkLostFormValues>({
    resolver: zodResolver(markLostFormSchema),
    defaultValues: { reasonCode: null, note: "" },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });

  const submit = useAsyncAction({
    action: (body: { lost_reason_id: string; lost_note: string | null }) => {
      const request = { to_stage: "lost" as const, expected_stage: lead.stage, ...body };
      return transition.mutateAsync({
        leadId: lead.id,
        body: request,
        idempotencyKey: idempotency.keyFor(request),
      });
    },
    logger: log,
    fn: "handleMarkLost",
    dataId: "LEAD-007",
    onSuccess: () => {
      toast.success("Lead marked as lost", { description: lead.customerName });
      closeSoon();
    },
    onError: (error) => {
      const reasonError = readFieldErrors(error)?.lost_reason_id;
      if (reasonError !== undefined) {
        form.setError("reasonCode", { type: "server", message: "Choose another reason" });
        return;
      }
      refusal.handle(error);
    },
  });

  const onValid = (values: MarkLostFormValues): void => {
    refusal.clear();
    const reason = reasons?.find((item) => item.code === values.reasonCode);
    if (reason === undefined) {
      form.setError("reasonCode", {
        type: "manual",
        message: "The list of reasons hasn't loaded — try again",
      });
      return;
    }
    const note = values.note.trim();
    void submit.run({ lost_reason_id: reason.id, lost_note: note === "" ? null : note });
  };

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        void form.handleSubmit(onValid)(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>Mark as lost</DialogTitle>
        <DialogDescription>
          {lead.customerName} leaves the pipeline. A lost lead can be reopened later.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="gap-4">
          <Controller
            control={form.control}
            name="reasonCode"
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.error ? true : undefined}>
                <FieldLabel htmlFor="lost-reason">Reason</FieldLabel>
                <LookupSelect
                  id="lost-reason"
                  list="lost-reasons"
                  placeholder="Why was it lost?"
                  value={field.value}
                  onValueChange={field.onChange}
                  onBlur={field.onBlur}
                  aria-invalid={fieldState.error ? true : undefined}
                  aria-describedby={fieldState.error ? "lost-reason-error" : undefined}
                />
                <FieldError id="lost-reason-error">{fieldState.error?.message}</FieldError>
              </Field>
            )}
          />
          <Field data-invalid={errors.note ? true : undefined}>
            <FieldLabel htmlFor="lost-note">
              Note
              <span className="font-normal text-subtle-foreground">(optional)</span>
            </FieldLabel>
            <Textarea
              id="lost-note"
              rows={3}
              aria-invalid={errors.note ? true : undefined}
              aria-describedby={errors.note ? "lost-note-error" : "lost-note-description"}
              {...form.register("note")}
            />
            {errors.note ? null : (
              <FieldDescription id="lost-note-description">
                Kept with the lead and on its history.
              </FieldDescription>
            )}
            <FieldError id="lost-note-error">{errors.note?.message}</FieldError>
          </Field>
        </FieldGroup>
        <RefusalAlert message={refusal.message} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          variant="destructive"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Marked lost"
          errorLabel="Not saved"
        >
          Mark as lost
        </Button>
      </DialogFooter>
    </form>
  );
}

function MarkWonForm({ lead, onClose }: FormProps): React.JSX.Element {
  const transition = useTransitionLead();
  const idempotency = useIdempotencyKey();
  const refusal = useRefusal(onClose);
  const closeSoon = useCloseAfterSuccess(onClose);

  const submit = useAsyncAction({
    action: () => {
      const request = {
        to_stage: "won" as const,
        expected_stage: lead.stage,
        lost_reason_id: null,
        lost_note: null,
      };
      return transition.mutateAsync({
        leadId: lead.id,
        body: request,
        idempotencyKey: idempotency.keyFor(request),
      });
    },
    logger: log,
    fn: "handleMarkWon",
    dataId: "LEAD-007",
    onSuccess: () => {
      toast.success("Lead won", { description: lead.customerName });
      closeSoon();
    },
    onError: refusal.handle,
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        refusal.clear();
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Mark as won</DialogTitle>
        <DialogDescription>
          {lead.customerName} moves from {LEAD_STAGE_LABELS[lead.stage]} to Won. A won lead is
          closed: its stage can no longer change.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <p className="text-sm text-muted-foreground">
          The lead needs an accepted quotation. If it has none yet, accept the quotation first.
        </p>
        <RefusalAlert message={refusal.message} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Won"
          errorLabel="Not saved"
        >
          Mark as won
        </Button>
      </DialogFooter>
    </form>
  );
}

function ReopenForm({ lead, onClose }: FormProps): React.JSX.Element {
  const reopen = useReopenLead();
  const idempotency = useIdempotencyKey();
  const refusal = useRefusal(onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const [note, setNote] = useState("");
  const tooLong = note.trim().length > LEAD_STAGE_NOTE_MAX_LENGTH;

  const submit = useAsyncAction({
    action: (text: string) => {
      const request = { note: text === "" ? null : text };
      return reopen.mutateAsync({
        leadId: lead.id,
        body: request,
        idempotencyKey: idempotency.keyFor(request),
      });
    },
    logger: log,
    fn: "handleReopen",
    dataId: "LEAD-007",
    onSuccess: (reopened) => {
      toast.success("Lead reopened", {
        description: `${reopened.customerName} is back at ${LEAD_STAGE_LABELS[reopened.stage]}.`,
      });
      closeSoon();
    },
    onError: refusal.handle,
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        if (tooLong) {
          return;
        }
        refusal.clear();
        void submit.run(note.trim());
      }}
    >
      <DialogHeader>
        <DialogTitle>Reopen lead</DialogTitle>
        <DialogDescription>
          {lead.customerName} goes back to the stage it was lost from. Its lost reason moves to the
          history.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <Field data-invalid={tooLong ? true : undefined}>
          <FieldLabel htmlFor="reopen-note">
            Why reopen it?
            <span className="font-normal text-subtle-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="reopen-note"
            rows={3}
            value={note}
            aria-invalid={tooLong ? true : undefined}
            aria-describedby={tooLong ? "reopen-note-error" : "reopen-note-description"}
            onChange={(event) => {
              setNote(event.target.value);
            }}
          />
          {tooLong ? null : (
            <FieldDescription id="reopen-note-description">Kept on the history.</FieldDescription>
          )}
          <FieldError id="reopen-note-error">
            {tooLong
              ? `Keep the note under ${String(LEAD_STAGE_NOTE_MAX_LENGTH)} characters`
              : undefined}
          </FieldError>
        </Field>
        <RefusalAlert message={refusal.message} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Reopening…"
          successLabel="Reopened"
          errorLabel="Not saved"
        >
          Reopen lead
        </Button>
      </DialogFooter>
    </form>
  );
}
