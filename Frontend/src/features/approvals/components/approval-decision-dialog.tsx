"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { useForm, useFormState } from "react-hook-form";
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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { useDecideApproval } from "@/features/approvals/api/approvals.mutations";
import {
  decisionFormSchema,
  type ApprovalDecision,
  type DecisionForm,
  type QueueRow,
} from "@/features/approvals/api/approvals.schemas";
import {
  DOC_TYPE_LABELS,
  decisionRefusal,
  documentTitle,
  remarkRequired,
} from "@/features/approvals/lib/approval-labels";
import { formatRate } from "@/features/quotations/lib/quotation-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/approvals/components/approval-decision-dialog.tsx",
  dataId: "APPR-001",
});

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

export interface PendingDecision {
  readonly row: QueueRow;
  readonly decision: ApprovalDecision;
}

export interface ApprovalDecisionDialogProps {
  /** The row and decision being confirmed; null when closed. */
  pending: PendingDecision | null;
  onClose: () => void;
}

/**
 * APPR-001 · Confirms an approval or a rejection. Rejecting needs a reason, which the person
 * who asked reads; approving takes one optionally (always on an Accounts step). A step that
 * someone else decided meanwhile closes the dialog and refreshes the inbox.
 */
export function ApprovalDecisionDialog({
  pending,
  onClose,
}: ApprovalDecisionDialogProps): React.JSX.Element {
  return (
    <Dialog
      open={pending !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent size="sm">
        {pending === null ? null : (
          <DecisionForm
            key={`${pending.row.stepId}-${pending.decision}`}
            {...pending}
            onClose={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function DecisionForm({
  row,
  decision,
  onClose,
}: PendingDecision & { onClose: () => void }): React.JSX.Element {
  const decide = useDecideApproval();
  const idempotency = useIdempotencyKey();
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const required = remarkRequired(decision, row.role);
  const form = useForm<DecisionForm>({
    resolver: zodResolver(decisionFormSchema(required)),
    defaultValues: { remark: "" },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    return () => {
      window.clearTimeout(timer.current);
    };
  }, []);

  const approve = decision === "approve";
  const title = documentTitle(row.docType, row.document.number);

  const submit = useAsyncAction({
    action: (remark: string | null) => {
      const body = { decision, remark };
      return decide.mutateAsync({
        stepId: row.stepId,
        body,
        idempotencyKey: idempotency.keyFor({ step: row.stepId, ...body }),
      });
    },
    logger: log,
    fn: approve ? "handleApprove" : "handleReject",
    dataId: "APPR-001",
    onSuccess: () => {
      idempotency.reset();
      toast.success(approve ? "Approved" : "Rejected", {
        description: `${DOC_TYPE_LABELS[row.docType]} · ${row.document.partyName}`,
      });
      timer.current = window.setTimeout(onClose, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      const view = decisionRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      if (view.remark !== null) {
        form.setError("remark", { type: "server", message: view.remark });
        return;
      }
      setRefusal({ title: view.title, message: view.message });
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => {
          const remark = values.remark.trim();
          return submit.run(remark === "" ? null : remark);
        })(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>
          {approve ? "Approve" : "Reject"} {DOC_TYPE_LABELS[row.docType].toLowerCase()}?
        </DialogTitle>
        <DialogDescription>
          {title} · {row.document.partyName} · {formatInr(row.document.total, { paise: true })}
          {row.document.discountPct === null
            ? ""
            : ` · ${formatRate(row.document.discountPct)} discount`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <p className="mb-4 text-sm text-muted-foreground">
          {row.docType === "quotation"
            ? approve
              ? "The officer can then send the quotation with this discount."
              : "The quotation stays a draft; the officer sees your reason and can change the discount."
            : approve
              ? "If yours is the last step, the order is approved."
              : "The order returns to draft, with your reason."}
        </p>
        <Field data-invalid={errors.remark ? true : undefined}>
          <FieldLabel htmlFor="decision-remark">
            {approve ? "Remark" : "Reason"}
            {required ? null : (
              <span className="font-normal text-subtle-foreground">(optional)</span>
            )}
          </FieldLabel>
          <Textarea
            id="decision-remark"
            rows={3}
            aria-invalid={errors.remark ? true : undefined}
            aria-describedby={
              errors.remark ? "decision-remark-error" : "decision-remark-description"
            }
            {...form.register("remark")}
          />
          {errors.remark ? null : (
            <FieldDescription id="decision-remark-description">
              {approve ? "Kept with the approval." : "The person who asked reads it."}
            </FieldDescription>
          )}
          <FieldError id="decision-remark-error">{errors.remark?.message}</FieldError>
        </Field>
        {refusal === null ? null : (
          <div
            role="alert"
            className="mt-4 flex flex-col gap-1 rounded-md border border-border bg-danger-soft p-3 text-sm"
          >
            <p className="font-medium text-danger">{refusal.title}</p>
            <p className="text-foreground">{refusal.message}</p>
          </div>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          variant={approve ? "primary" : "destructive"}
          state={submit.state}
          loadingLabel={approve ? "Approving…" : "Rejecting…"}
          successLabel={approve ? "Approved" : "Rejected"}
          errorLabel="Not saved"
        >
          {approve ? "Approve" : "Reject"}
        </Button>
      </DialogFooter>
    </form>
  );
}
