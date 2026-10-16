"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { useForm, useFormState, type UseFormReturn } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { buttonVariants } from "@/components/ui/button-variants";
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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import {
  useDeleteQuotation,
  useRequestQuotationApproval,
  useReviseQuotation,
  useSendQuotation,
  useTransitionQuotation,
} from "@/features/quotations/api/quotations.mutations";
import { quotationKeys } from "@/features/quotations/api/quotations.queries";
import {
  quotationRemarkFormSchema,
  type Quotation,
  type QuotationAnswer,
  type QuotationRemarkForm,
} from "@/features/quotations/api/quotations.schemas";
import { quotationTitle, formatRate } from "@/features/quotations/lib/quotation-labels";
import {
  ANSWER_LABELS,
  lifecycleRefusal,
  roleLabel,
} from "@/features/quotations/lib/quotation-lifecycle";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { isApiError } from "@/lib/api/errors";
import { formatIndianPhone, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/quotations/components/quotation-action-dialog.tsx",
  dataId: "QUOT-006",
});

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

/** Which action's dialog is open. */
export type QuotationDialog =
  | { readonly kind: "send" }
  | { readonly kind: "approval"; readonly why: "required" | "void" | "returned" }
  | { readonly kind: "answer"; readonly to: QuotationAnswer }
  | { readonly kind: "revise" }
  | { readonly kind: "delete" };

export interface QuotationActionDialogProps {
  quotation: Quotation;
  /** The open dialog; null when none. */
  dialog: QuotationDialog | null;
  onClose: () => void;
}

/**
 * QUOT-006 … QUOT-011 · Confirms an action on a quotation: send, ask for discount approval,
 * record the customer's answer, revise, or delete a draft. A refusal because someone else
 * moved the quotation closes the dialog, says so, and shows the latest; any other refusal
 * stays in the dialog with what to do next.
 */
export function QuotationActionDialog({
  quotation,
  dialog,
  onClose,
}: QuotationActionDialogProps): React.JSX.Element {
  return (
    <Dialog
      open={dialog !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent size="sm">
        {dialog?.kind === "send" ? <SendForm quotation={quotation} onClose={onClose} /> : null}
        {dialog?.kind === "approval" ? (
          <ApprovalForm quotation={quotation} why={dialog.why} onClose={onClose} />
        ) : null}
        {dialog?.kind === "answer" ? (
          <AnswerForm quotation={quotation} to={dialog.to} onClose={onClose} />
        ) : null}
        {dialog?.kind === "revise" ? <ReviseForm quotation={quotation} onClose={onClose} /> : null}
        {dialog?.kind === "delete" ? <DeleteForm quotation={quotation} onClose={onClose} /> : null}
      </DialogContent>
    </Dialog>
  );
}

interface FormProps {
  quotation: Quotation;
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

interface Refusal {
  readonly title: string;
  readonly message: string;
  /** Prices changed or the draft is empty: the fix is in the builder. */
  readonly editDraft: boolean;
}

/** A refusal: stale ones close the dialog with a toast and re-read the quotation. */
function useRefusal(
  quotationId: string,
  onClose: () => void,
): { refusal: Refusal | null; handle: (error: unknown) => void; clear: () => void } {
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const queryClient = useQueryClient();
  return {
    refusal,
    handle: (error) => {
      const view = lifecycleRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        void queryClient.invalidateQueries({ queryKey: quotationKeys.detail(quotationId) });
        void queryClient.invalidateQueries({ queryKey: quotationKeys.versionLists() });
        onClose();
        return;
      }
      const code = isApiError(error) ? error.code : null;
      setRefusal({
        title: view.title,
        message: view.message,
        editDraft: code === "rate_changed" || code === "no_lines",
      });
    },
    clear: () => {
      setRefusal(null);
    },
  };
}

function RefusalAlert({
  refusal,
  quotationId,
}: {
  refusal: Refusal | null;
  quotationId: string;
}): React.JSX.Element | null {
  if (refusal === null) {
    return null;
  }
  return (
    <div
      role="alert"
      className="mt-4 flex flex-col gap-2 rounded-md border border-border bg-danger-soft p-3 text-sm"
    >
      <p className="font-medium text-danger">{refusal.title}</p>
      <p className="text-foreground">{refusal.message}</p>
      {refusal.editDraft ? (
        <Link
          href={`/quotations/${quotationId}/edit`}
          className={buttonVariants({ variant: "outline", size: "sm", className: "self-start" })}
        >
          Open the draft
        </Link>
      ) : null}
    </div>
  );
}

/** The optional remark on an answer or an approval request. */
function RemarkField({
  form,
  id,
  label,
  description,
}: {
  form: UseFormReturn<QuotationRemarkForm>;
  id: string;
  label: string;
  description: string;
}): React.JSX.Element {
  const { errors } = useFormState({ control: form.control });
  return (
    <Field data-invalid={errors.remark ? true : undefined}>
      <FieldLabel htmlFor={id}>
        {label}
        <span className="font-normal text-muted-foreground">(optional)</span>
      </FieldLabel>
      <Textarea
        id={id}
        rows={3}
        aria-invalid={errors.remark ? true : undefined}
        aria-describedby={errors.remark ? `${id}-error` : `${id}-description`}
        {...form.register("remark")}
      />
      {errors.remark ? null : (
        <FieldDescription id={`${id}-description`}>{description}</FieldDescription>
      )}
      <FieldError id={`${id}-error`}>{errors.remark?.message}</FieldError>
    </Field>
  );
}

function useRemarkForm(): UseFormReturn<QuotationRemarkForm> {
  return useForm<QuotationRemarkForm>({
    resolver: zodResolver(quotationRemarkFormSchema),
    defaultValues: { remark: "" },
    mode: "onTouched",
  });
}

function orNull(remark: string): string | null {
  const trimmed = remark.trim();
  return trimmed === "" ? null : trimmed;
}

// ── send (QUOT-006) ─────────────────────────────────────────────────────────────

type Channel = "whatsapp" | "none";

function SendForm({ quotation, onClose }: FormProps): React.JSX.Element {
  const send = useSendQuotation();
  const idempotency = useIdempotencyKey();
  const { refusal, handle, clear } = useRefusal(quotation.id, onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const hasMobile = quotation.party.mobile !== "";
  const [channel, setChannel] = useState<Channel>(hasMobile ? "whatsapp" : "none");

  const submit = useAsyncAction({
    action: () => {
      const body = { channel, expected_status: "draft" as const };
      return send.mutateAsync({
        quotationId: quotation.id,
        input: { body, idempotencyKey: idempotency.keyFor({ id: quotation.id, ...body }) },
      });
    },
    logger: log,
    fn: "handleSendQuotation",
    dataId: "QUOT-006",
    onSuccess: (sent) => {
      idempotency.reset();
      toast.success("Quotation sent", {
        description: `${quotationTitle(sent)} · the PDF is being prepared`,
      });
      closeSoon();
    },
    onError: (error) => {
      // A rate change needs a new save, so the next send is a new request.
      idempotency.reset();
      handle(error);
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        clear();
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Send the quotation</DialogTitle>
        <DialogDescription>
          {quotation.party.name} · {formatInr(quotation.totals.total, { paise: true })}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <div className="flex flex-col gap-4">
          <RadioGroup<Channel>
            aria-label="How the customer gets it"
            value={channel}
            onValueChange={setChannel}
            className="gap-3"
          >
            <label className="flex items-start gap-3 rounded-lg border border-border p-3 text-sm has-data-checked:border-highlight-border has-data-disabled:opacity-60">
              <RadioGroupItem value="whatsapp" disabled={!hasMobile} className="mt-0.5" />
              <span className="flex flex-col gap-0.5">
                <span className="font-medium text-foreground">Send on WhatsApp</span>
                <span className="text-muted-foreground">
                  {hasMobile
                    ? `To ${formatIndianPhone(quotation.party.mobile)}, as soon as the PDF is ready.`
                    : "The party has no mobile. Edit the draft to add one."}
                </span>
              </span>
            </label>
            <label className="flex items-start gap-3 rounded-lg border border-border p-3 text-sm has-data-checked:border-highlight-border">
              <RadioGroupItem value="none" className="mt-0.5" />
              <span className="flex flex-col gap-0.5">
                <span className="font-medium text-foreground">Don&apos;t send a message</span>
                <span className="text-muted-foreground">
                  Copy the link from the quotation and share it yourself.
                </span>
              </span>
            </label>
          </RadioGroup>
          <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-muted-foreground">
            <li>It gets its number and is valid for 45 days.</li>
            <li>A qualified lead moves to Quoted.</li>
            <li>A sent quotation isn&apos;t edited again: it is revised.</li>
            {quotation.isProvisional ? (
              <li className="text-warning">
                Some rates are stand-ins: the PDF carries an Indicative pricing banner.
              </li>
            ) : null}
          </ul>
        </div>
        <RefusalAlert refusal={refusal} quotationId={quotation.id} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Sending…"
          successLabel="Sent"
          errorLabel="Not sent"
        >
          Send quotation
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── discount approval (QUOT-007) ─────────────────────────────────────────────────

function ApprovalForm({
  quotation,
  why,
  onClose,
}: FormProps & { why: "required" | "void" | "returned" }): React.JSX.Element {
  const request = useRequestQuotationApproval();
  const idempotency = useIdempotencyKey();
  const { refusal, handle, clear } = useRefusal(quotation.id, onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const form = useRemarkForm();
  const discount = quotation.discount;
  const returned = quotation.approval?.steps.find((step) => step.decision === "reject") ?? null;

  const submit = useAsyncAction({
    action: (remark: string | null) => {
      const body = { remark };
      return request.mutateAsync({
        quotationId: quotation.id,
        input: { body, idempotencyKey: idempotency.keyFor({ id: quotation.id, ...body }) },
      });
    },
    logger: log,
    fn: "handleRequestApproval",
    dataId: "QUOT-007",
    onSuccess: (asked) => {
      idempotency.reset();
      const role = asked.approval?.steps[0]?.role;
      toast.success("Approval asked", {
        description:
          role === undefined
            ? "A manager will review the discount."
            : `A ${roleLabel(role)} will review the discount.`,
      });
      closeSoon();
    },
    onError: handle,
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        clear();
        void form.handleSubmit((values) => submit.run(orNull(values.remark)))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>Ask for discount approval</DialogTitle>
        <DialogDescription>
          {discount === null
            ? "A manager above you approves the discount; then you can send."
            : `The discount is ${formatRate(discount.effectivePct)}; your limit is ${discount.ownerLimitPct === null ? "none" : formatRate(discount.ownerLimitPct)}. A manager above you approves it; then you can send.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <div className="flex flex-col gap-4">
          {why === "void" ? (
            <p className="rounded-md bg-warning-soft p-3 text-sm text-foreground">
              The earlier approval no longer applies: the figures changed after it was given.
            </p>
          ) : null}
          {why === "returned" ? (
            <p className="rounded-md bg-danger-soft p-3 text-sm text-foreground">
              The last request was refused
              {returned?.remark === null || returned === null ? "." : `: “${returned.remark}”`}
            </p>
          ) : null}
          <RemarkField
            form={form}
            id="approval-remark"
            label="Why is this discount needed?"
            description="The approver reads it with the figures."
          />
        </div>
        <RefusalAlert refusal={refusal} quotationId={quotation.id} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Asking…"
          successLabel="Asked"
          errorLabel="Not asked"
        >
          Ask for approval
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── the customer's answer (QUOT-008) ─────────────────────────────────────────────

const ANSWER_COPY: Readonly<
  Record<QuotationAnswer, { title: string; explain: string; submit: string; done: string }>
> = {
  accepted: {
    title: "Mark as accepted",
    explain: "The customer accepted it. The lead moves to Won.",
    submit: "Mark accepted",
    done: "Marked accepted",
  },
  negotiation: {
    title: "Mark as in negotiation",
    explain:
      "The customer wants to talk terms. The lead moves to Negotiation; revise the quotation once new terms are agreed.",
    submit: "Mark in negotiation",
    done: "Marked in negotiation",
  },
  rejected: {
    title: "Mark as rejected",
    explain:
      "The customer turned it down. The lead doesn't move: revise the quotation, or mark the lead lost from its page.",
    submit: "Mark rejected",
    done: "Marked rejected",
  },
};

function AnswerForm({
  quotation,
  to,
  onClose,
}: FormProps & { to: QuotationAnswer }): React.JSX.Element {
  const transition = useTransitionQuotation();
  const idempotency = useIdempotencyKey();
  const { refusal, handle, clear } = useRefusal(quotation.id, onClose);
  const closeSoon = useCloseAfterSuccess(onClose);
  const form = useRemarkForm();
  const copy = ANSWER_COPY[to];

  const submit = useAsyncAction({
    action: (remark: string | null) => {
      const body = { to, remark, expected_status: quotation.status };
      return transition.mutateAsync({
        quotationId: quotation.id,
        input: { body, idempotencyKey: idempotency.keyFor({ id: quotation.id, ...body }) },
      });
    },
    logger: log,
    fn: "handleRecordAnswer",
    dataId: "QUOT-008",
    onSuccess: (answered) => {
      idempotency.reset();
      toast.success(copy.done, {
        description:
          answered.lead?.stage === "won"
            ? `${quotationTitle(answered)} · the lead is Won`
            : quotationTitle(answered),
      });
      closeSoon();
    },
    onError: handle,
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        clear();
        void form.handleSubmit((values) => submit.run(orNull(values.remark)))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>{copy.title}</DialogTitle>
        <DialogDescription>
          {quotationTitle(quotation)} · {quotation.party.name}. {copy.explain}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <RemarkField
          form={form}
          id="answer-remark"
          label="What the customer said"
          description="Kept on the quotation's history."
        />
        <RefusalAlert refusal={refusal} quotationId={quotation.id} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          variant={to === "rejected" ? "destructive" : "primary"}
          state={submit.state}
          loadingLabel="Saving…"
          successLabel={ANSWER_LABELS[to]}
          errorLabel="Not saved"
        >
          {copy.submit}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── revise (QUOT-009) ────────────────────────────────────────────────────────────

function ReviseForm({ quotation, onClose }: FormProps): React.JSX.Element {
  const revise = useReviseQuotation();
  const idempotency = useIdempotencyKey();
  const router = useRouter();
  const { refusal, handle, clear } = useRefusal(quotation.id, onClose);
  const next = quotation.version + 1;

  const submit = useAsyncAction({
    action: () => {
      const body = { price_effective_date: null, expected_status: quotation.status };
      return revise.mutateAsync({
        quotationId: quotation.id,
        input: { body, idempotencyKey: idempotency.keyFor({ id: quotation.id, ...body }) },
      });
    },
    logger: log,
    fn: "handleReviseQuotation",
    dataId: "QUOT-009",
    onSuccess: (revision) => {
      idempotency.reset();
      toast.success(`Version ${String(revision.version)} drafted`, {
        description: "Check the prices, change what was agreed, then send it.",
      });
      router.push(`/quotations/${revision.id}`);
    },
    onError: handle,
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        clear();
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Revise into version {next}</DialogTitle>
        <DialogDescription>
          A new draft of {quotationTitle(quotation)} with the same items, priced at today&apos;s
          rates.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <ul className="flex list-disc flex-col gap-1 pl-5 text-sm text-muted-foreground">
          <li>Version {quotation.version} stays as it is, with its PDF and link.</li>
          <li>Sending version {next} marks this one as replaced.</li>
          <li>Any item whose rate or tax changed is pointed out on the new draft.</li>
        </ul>
        <RefusalAlert refusal={refusal} quotationId={quotation.id} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Revising…"
          successLabel="Drafted"
          errorLabel="Not revised"
        >
          Revise
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── delete a draft (QUOT-011) ────────────────────────────────────────────────────

function DeleteForm({ quotation, onClose }: FormProps): React.JSX.Element {
  const remove = useDeleteQuotation(quotation.lead?.id ?? null);
  const idempotency = useIdempotencyKey();
  const router = useRouter();
  const { refusal, handle, clear } = useRefusal(quotation.id, onClose);

  const submit = useAsyncAction({
    action: () => {
      const body = { expected_status: "draft" as const };
      return remove.mutateAsync({
        quotationId: quotation.id,
        input: { body, idempotencyKey: idempotency.keyFor({ id: quotation.id, ...body }) },
      });
    },
    logger: log,
    fn: "handleDeleteDraft",
    dataId: "QUOT-011",
    onSuccess: () => {
      toast.success("Draft deleted", { description: quotation.party.name });
      router.push(quotation.lead === null ? "/quotations" : `/leads/${quotation.lead.id}`);
    },
    onError: handle,
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        clear();
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Delete this draft?</DialogTitle>
        <DialogDescription>
          {quotationTitle(quotation)} for {quotation.party.name} ·{" "}
          {formatInr(quotation.totals.total, { paise: true })}. A deleted draft can&apos;t be
          brought back.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        {quotation.approval?.status === "pending" ? (
          <p className="text-sm text-muted-foreground">
            Its discount approval request is withdrawn too.
          </p>
        ) : null}
        <RefusalAlert refusal={refusal} quotationId={quotation.id} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          variant="destructive"
          state={submit.state}
          loadingLabel="Deleting…"
          successLabel="Deleted"
          errorLabel="Not deleted"
        >
          Delete draft
        </Button>
      </DialogFooter>
    </form>
  );
}
