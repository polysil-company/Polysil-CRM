"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import type * as React from "react";
import { useForm, useFormState, useWatch } from "react-hook-form";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { usePutApprovalThreshold } from "@/features/approvals/api/approvals.mutations";
import { approvalKeys } from "@/features/approvals/api/approvals.queries";
import {
  limitFormSchema,
  type ApprovalDocType,
  type LimitForm,
  type LimitRole,
  type Threshold,
} from "@/features/approvals/api/approvals.schemas";
import { limitRoleLabel } from "@/features/approvals/lib/approval-labels";
import {
  boundsFor,
  boundsHint,
  formatLimit,
  ladderFor,
  limitRefusal,
  mayBeUnlimited,
  outOfBounds,
  type LimitRefusal,
} from "@/features/approvals/lib/approval-limits";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/approvals/components/approval-limit-dialog.tsx",
  dataId: "APPR-002",
});

/** Long enough to see the success check before the dialog closes. */
const CLOSE_AFTER_SUCCESS_MS = 600;

/** The limit being changed: a document's ladder, one role, company-wide or a territory's. */
export interface LimitTarget {
  readonly docType: ApprovalDocType;
  readonly role: LimitRole;
  readonly territory: Threshold["territory"];
}

export interface ApprovalLimitDialogProps {
  rows: readonly Threshold[];
  target: LimitTarget | null;
  onClose: () => void;
}

/** APPR-002 · Changes one role's limit. */
export function ApprovalLimitDialog({
  rows,
  target,
  onClose,
}: ApprovalLimitDialogProps): React.JSX.Element {
  return (
    <Dialog
      open={target !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <DialogContent size="sm">
        {target === null ? null : <LimitFormBody rows={rows} target={target} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function LimitFormBody({
  rows,
  target,
  onClose,
}: {
  rows: readonly Threshold[];
  target: LimitTarget;
  onClose: () => void;
}): React.JSX.Element {
  const put = usePutApprovalThreshold();
  const idempotency = useIdempotencyKey();
  const queryClient = useQueryClient();
  const [refusal, setRefusal] = useState<LimitRefusal | null>(null);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    return () => {
      window.clearTimeout(timer.current);
    };
  }, []);

  const unit: Threshold["unit"] = target.docType === "sales_order" ? "inr" : "pct";
  const territoryId = target.territory?.id ?? null;
  const ladder = ladderFor(rows, target.docType, territoryId);
  const current = ladder.find((step) => step.role === target.role)?.row ?? null;
  const bounds = boundsFor(ladder, target.role);
  const unlimitedAllowed = mayBeUnlimited(target.docType, target.role);
  const who = limitRoleLabel(target.role);
  const what = target.docType === "sales_order" ? "order limit" : "discount limit";
  const where = target.territory === null ? "company-wide" : `in ${target.territory.name}`;

  const form = useForm<LimitForm>({
    resolver: zodResolver(limitFormSchema),
    defaultValues: {
      unit,
      noLimit: current !== null && current.maxAmount === null,
      amount:
        current?.maxAmount === null || current === null ? "" : String(Number(current.maxAmount)),
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const noLimit = useWatch({ control: form.control, name: "noLimit" });
  const hint = boundsHint(bounds, unit);

  const submit = useAsyncAction({
    action: (maxAmount: string | null) => {
      const body = {
        doc_type: target.docType,
        role: target.role,
        territory_id: territoryId,
        max_amount: maxAmount,
      };
      return put.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleSaveLimit",
    dataId: "APPR-002",
    onSuccess: () => {
      idempotency.reset();
      toast.success(`${who}'s ${what} changed`, {
        description: "It applies from the next order or discount request.",
      });
      timer.current = window.setTimeout(onClose, CLOSE_AFTER_SUCCESS_MS);
    },
    onError: (error) => {
      const view = limitRefusal(error);
      if (view.field !== null) {
        form.setError("amount", { type: "server", message: view.field });
      }
      setRefusal(view);
      // The levels may have changed under us: show the latest behind the dialog.
      void queryClient.invalidateQueries({ queryKey: approvalKeys.thresholds() });
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => {
          if (values.noLimit) {
            return submit.run(null);
          }
          const breaks = outOfBounds(Number(values.amount), bounds, unit);
          if (breaks !== null) {
            form.setError("amount", { type: "bounds", message: breaks });
            return undefined;
          }
          return submit.run(Number(values.amount).toFixed(2));
        })(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>
          {who}&apos;s {what}
        </DialogTitle>
        <DialogDescription>
          {current === null
            ? "Not set yet"
            : `Now ${formatLimit(current.maxAmount, unit).toLowerCase()}`}
          , {where}.{" "}
          {target.docType === "sales_order"
            ? "Orders up to this value, including GST, stop at this level."
            : target.role === "field_officer"
              ? "Discounts up to this need no approval."
              : "Discounts up to this are approved at this level."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <div className="flex flex-col gap-4">
          <Field data-invalid={errors.amount ? true : undefined}>
            <FieldLabel htmlFor="limit-amount">
              {unit === "inr" ? "Limit in rupees" : "Limit in percent"}
            </FieldLabel>
            <Input
              id="limit-amount"
              inputMode="decimal"
              disabled={noLimit}
              placeholder={unit === "inr" ? "100000" : "10"}
              aria-invalid={errors.amount ? true : undefined}
              aria-describedby={errors.amount ? "limit-amount-error" : "limit-amount-description"}
              className="tabular-nums"
              {...form.register("amount")}
            />
            {errors.amount || hint === null ? null : (
              <FieldDescription id="limit-amount-description">{hint}</FieldDescription>
            )}
            <FieldError id="limit-amount-error">{errors.amount?.message}</FieldError>
          </Field>
          {unlimitedAllowed ? (
            <div className="flex items-center gap-2">
              <Checkbox
                id="limit-none"
                checked={noLimit}
                onCheckedChange={(checked) => {
                  form.setValue("noLimit", checked, { shouldDirty: true });
                  form.clearErrors("amount");
                }}
              />
              <Label htmlFor="limit-none" className="font-normal">
                No limit — the top of the ladder approves any{" "}
                {target.docType === "sales_order" ? "value" : "discount"}
              </Label>
            </div>
          ) : null}
        </div>
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
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Save limit
        </Button>
      </DialogFooter>
    </form>
  );
}
