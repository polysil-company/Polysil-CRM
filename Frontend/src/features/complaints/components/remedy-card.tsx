"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Undo02Icon } from "@hugeicons/core-free-icons";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";
import { Controller, useForm, useFormState, useWatch } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge, type BadgeVariant } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Textarea } from "@/components/ui/textarea";
import { useChooseRemedy, useWithdrawRemedy } from "@/features/complaints/api/complaints.mutations";
import type { Complaint, RemedyKind } from "@/features/complaints/api/complaints.schemas";
import { complaintRefusal } from "@/features/complaints/lib/complaint-labels";
import { ApprovalChain } from "@/features/orders/components/order-approval";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { COMPLAINT_TEXT_MAX, Refusal, useCloseLater } from "./complaint-dialog-parts";
import { DealerPicker, type DealerChoice } from "./dealer-picker";

const log = createLogger({
  file: "features/complaints/components/remedy-card.tsx",
  dataId: "CMPL-007",
});

/** The largest refund the form takes: a typo guard, not a business limit. */
const REFUND_MAX = 10_000_000;

export const REMEDY_LABELS: Readonly<Record<RemedyKind, string>> = {
  refund: "Refund",
  replacement: "Replacement",
  none: "No action",
};

type RemedyStatus = NonNullable<Complaint["remedy"]>["status"];

const REMEDY_STATUS: Readonly<Record<RemedyStatus, { label: string; badge: BadgeVariant }>> = {
  pending: { label: "Under way", badge: "warning" },
  completed: { label: "Done", badge: "success" },
  rejected: { label: "Turned down", badge: "danger" },
  withdrawn: { label: "Withdrawn", badge: "neutral" },
  cancelled: { label: "Cancelled", badge: "neutral" },
};

const KIND_HINTS: Readonly<Record<RemedyKind, string>> = {
  refund: "Managers approve it by amount, then Accounts pays and records the reference.",
  replacement: "A free order for the defective quantity goes to Dispatch.",
  none: "QC found a defect but no remedy is due. The complaint closes now.",
};

/**
 * CMPL-007 · The remedy: what QC chose, and how far it has got — a refund's approval steps
 * and payment reference, or the replacement order. QC chooses one once a defect is found,
 * and may withdraw it while it is open; a refund turned down at approval returns here.
 */
export function RemedyCard({ complaint }: { complaint: Complaint }): React.JSX.Element | null {
  const [dialog, setDialog] = useState<"choose" | "withdraw" | null>(null);
  const { remedy, can } = complaint;
  if (remedy === null && !can.remedy) return null;
  const close = (): void => {
    setDialog(null);
  };
  const again = remedy !== null && (remedy.status === "rejected" || remedy.status === "withdrawn");

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <CardTitle level={3}>Remedy</CardTitle>
          {remedy === null ? (
            <CardDescription>QC found a defect. Choose how to set it right.</CardDescription>
          ) : null}
        </div>
        {remedy === null ? null : (
          <Badge variant={REMEDY_STATUS[remedy.status].badge} dot>
            {REMEDY_STATUS[remedy.status].label}
          </Badge>
        )}
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-sm">
        {remedy === null ? null : <RemedyDetails remedy={remedy} />}
        {again && can.remedy ? (
          <p role="note" className="rounded-md bg-muted p-2 text-xs text-muted-foreground">
            {remedy.status === "rejected"
              ? "The refund was turned down at approval. Choose the remedy again."
              : "The remedy was withdrawn. Choose it again."}
          </p>
        ) : null}
        {can.remedy || can.withdraw ? (
          <div className="flex flex-wrap gap-2">
            {can.remedy ? (
              <Button
                size="sm"
                onClick={() => {
                  setDialog("choose");
                }}
              >
                {remedy === null ? "Choose the remedy" : "Choose again"}
              </Button>
            ) : null}
            {can.withdraw ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  setDialog("withdraw");
                }}
              >
                <Icon icon={Undo02Icon} />
                Withdraw
              </Button>
            ) : null}
          </div>
        ) : null}
      </CardContent>

      <Dialog
        open={dialog !== null}
        onOpenChange={(open) => {
          if (!open) close();
        }}
      >
        <DialogContent size={dialog === "withdraw" ? "sm" : "md"}>
          {dialog === "choose" ? <ChooseRemedyForm complaint={complaint} onClose={close} /> : null}
          {dialog === "withdraw" ? <WithdrawForm complaint={complaint} onClose={close} /> : null}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function RemedyDetails({
  remedy,
}: {
  remedy: NonNullable<Complaint["remedy"]>;
}): React.JSX.Element {
  const { refund, replacementOrder } = remedy;
  return (
    <>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        <dt className="text-muted-foreground">Remedy</dt>
        <dd className="font-medium text-foreground">{REMEDY_LABELS[remedy.kind]}</dd>
        {refund === null ? null : (
          <>
            <dt className="text-muted-foreground">Amount</dt>
            <dd className="font-medium text-foreground tabular-nums">
              {formatInr(refund.amount, { paise: true })}
            </dd>
            {refund.payeeName === null ? null : (
              <>
                <dt className="text-muted-foreground">Paid to</dt>
                <dd className="wrap-break-word text-foreground">{refund.payeeName}</dd>
              </>
            )}
            {refund.paidThrough === null ? null : (
              <>
                <dt className="text-muted-foreground">Through</dt>
                <dd className="wrap-break-word text-foreground">{refund.paidThrough.name}</dd>
              </>
            )}
            {refund.paymentReference === null ? null : (
              <>
                <dt className="text-muted-foreground">Payment ref.</dt>
                <dd className="font-mono text-foreground">{refund.paymentReference}</dd>
              </>
            )}
          </>
        )}
        {replacementOrder === null ? null : (
          <>
            <dt className="text-muted-foreground">Order</dt>
            <dd>
              <Link
                href={`/sales-orders/${replacementOrder.id}`}
                className="font-medium text-foreground underline-offset-2 hover:underline"
              >
                {replacementOrder.orderNo ?? "The replacement order"}
              </Link>
            </dd>
          </>
        )}
      </dl>
      {remedy.remark === null ? null : (
        <p className="wrap-break-word whitespace-pre-line text-muted-foreground">{remedy.remark}</p>
      )}
      {refund?.approval == null || refund.approval.steps.length === 0 ? null : (
        <ApprovalChain approval={refund.approval} compact />
      )}
      <p className="text-xs text-subtle-foreground">
        Chosen{remedy.chosenBy === null ? "" : ` by ${remedy.chosenBy.name}`}{" "}
        <RelativeDate value={remedy.chosenAt} />
      </p>
    </>
  );
}

// ── choose (CMPL-007) ──────────────────────────────────────────────────────────────

interface RemedyForm {
  kind: RemedyKind;
  amount: string;
  payeeName: string;
  paidThrough: DealerChoice | null;
  remark: string;
}

const remedySchema: z.ZodType<RemedyForm, RemedyForm> = z
  .object({
    kind: z.enum(["refund", "replacement", "none"]),
    amount: z.string(),
    payeeName: z.string().max(200, "Keep it under 200 characters."),
    paidThrough: z.custom<DealerChoice | null>(() => true),
    remark: z
      .string()
      .trim()
      .min(1, "Say why this remedy.")
      .max(COMPLAINT_TEXT_MAX, "Keep it under 2000 characters."),
  })
  .superRefine((values, ctx) => {
    if (values.kind !== "refund") return;
    const amount = values.amount.trim();
    if (!/^\d+(\.\d{1,2})?$/.test(amount) || Number(amount) <= 0) {
      ctx.addIssue({
        code: "custom",
        path: ["amount"],
        message: "Enter an amount above 0, in rupees, with up to two decimals.",
      });
    } else if (Number(amount) > REFUND_MAX) {
      ctx.addIssue({
        code: "custom",
        path: ["amount"],
        message: "That looks too large. Check it.",
      });
    }
    if (values.payeeName.trim() === "") {
      ctx.addIssue({ code: "custom", path: ["payeeName"], message: "Who receives the refund?" });
    }
  });

const SERVER_FIELDS = {
  amount: "amount",
  payee_name: "payeeName",
  remark: "remark",
} as const satisfies Readonly<Record<string, keyof RemedyForm>>;

function ChooseRemedyForm({
  complaint,
  onClose,
}: {
  complaint: Complaint;
  onClose: () => void;
}): React.JSX.Element {
  const choose = useChooseRemedy();
  const idempotency = useIdempotencyKey();
  const closeLater = useCloseLater(onClose);
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const form = useForm<RemedyForm>({
    resolver: zodResolver(remedySchema),
    defaultValues: {
      kind: "refund",
      amount: "",
      payeeName: complaint.contactName,
      paidThrough:
        complaint.partner === null || complaint.partner.hidden
          ? null
          : { id: complaint.partner.id, name: complaint.partner.name ?? "A dealer" },
      remark: "",
    },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const kind = useWatch({ control: form.control, name: "kind" });

  const submit = useAsyncAction({
    action: (values: RemedyForm) => {
      const refund = values.kind === "refund";
      const body = {
        kind: values.kind,
        amount: refund ? values.amount.trim() : null,
        payee_name: refund ? values.payeeName.trim() : null,
        paid_through_partner_id: refund ? (values.paidThrough?.id ?? null) : null,
        remark: values.remark.trim(),
      };
      return choose.mutateAsync({
        complaintId: complaint.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: complaint.id, ...body }),
      });
    },
    logger: log,
    fn: "handleChooseRemedy",
    dataId: "CMPL-007",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(
        saved.status === "closed"
          ? "Closed with no remedy"
          : saved.remedy?.kind === "refund"
            ? "Refund sent for approval"
            : "Replacement order raised",
        { description: saved.number ?? undefined },
      );
      closeLater();
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
        return;
      }
      let placed = false;
      for (const [api, name] of Object.entries(SERVER_FIELDS)) {
        const message = view.fields?.[api];
        if (message !== undefined) {
          form.setError(name, { type: "server", message });
          placed = true;
        }
      }
      if (!placed) setRefusal({ title: view.title, message: view.message });
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        setRefusal(null);
        void form.handleSubmit((values) => submit.run(values))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>Choose the remedy</DialogTitle>
        <DialogDescription>
          For {complaint.number ?? "this complaint"}, from {complaint.contactName}.
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <FieldGroup className="flex flex-col gap-4">
          <Controller
            control={form.control}
            name="kind"
            render={({ field }) => (
              <Field>
                <FieldLabel id="remedy-kind-label">Remedy</FieldLabel>
                <RadioGroup<RemedyKind>
                  aria-labelledby="remedy-kind-label"
                  aria-describedby="remedy-kind-hint"
                  value={field.value}
                  onValueChange={(value) => {
                    field.onChange(value);
                  }}
                  className="flex flex-col gap-2 sm:flex-row sm:gap-6"
                >
                  {(["refund", "replacement", "none"] as const).map((value) => (
                    <label key={value} className="flex items-center gap-2 text-sm">
                      <RadioGroupItem value={value} />
                      {REMEDY_LABELS[value]}
                    </label>
                  ))}
                </RadioGroup>
                <FieldDescription id="remedy-kind-hint">{KIND_HINTS[kind]}</FieldDescription>
              </Field>
            )}
          />
          {kind === "refund" ? (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field data-invalid={errors.amount ? true : undefined}>
                  <FieldLabel htmlFor="remedy-amount">Amount (₹)</FieldLabel>
                  <Input
                    id="remedy-amount"
                    inputMode="decimal"
                    autoComplete="off"
                    placeholder="0.00"
                    aria-invalid={errors.amount ? true : undefined}
                    aria-describedby={errors.amount ? "remedy-amount-error" : undefined}
                    {...form.register("amount")}
                  />
                  <FieldError id="remedy-amount-error">{errors.amount?.message}</FieldError>
                </Field>
                <Field data-invalid={errors.payeeName ? true : undefined}>
                  <FieldLabel htmlFor="remedy-payee">Paid to</FieldLabel>
                  <Input
                    id="remedy-payee"
                    autoComplete="off"
                    aria-invalid={errors.payeeName ? true : undefined}
                    aria-describedby={errors.payeeName ? "remedy-payee-error" : undefined}
                    {...form.register("payeeName")}
                  />
                  <FieldError id="remedy-payee-error">{errors.payeeName?.message}</FieldError>
                </Field>
              </div>
              <Controller
                control={form.control}
                name="paidThrough"
                render={({ field }) => (
                  <Field>
                    <FieldLabel htmlFor="remedy-dealer">
                      Through a dealer
                      <span className="font-normal text-subtle-foreground">(optional)</span>
                    </FieldLabel>
                    <DealerPicker
                      id="remedy-dealer"
                      value={field.value}
                      onValueChange={field.onChange}
                    />
                    <FieldDescription>When the dealer passes the refund on.</FieldDescription>
                  </Field>
                )}
              />
            </>
          ) : null}
          <Field data-invalid={errors.remark ? true : undefined}>
            <FieldLabel htmlFor="remedy-remark">Why this remedy</FieldLabel>
            <Textarea
              id="remedy-remark"
              rows={3}
              aria-invalid={errors.remark ? true : undefined}
              aria-describedby={errors.remark ? "remedy-remark-error" : undefined}
              {...form.register("remark")}
            />
            <FieldError id="remedy-remark-error">{errors.remark?.message}</FieldError>
          </Field>
        </FieldGroup>
        <Refusal refusal={refusal} />
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
          {kind === "refund"
            ? "Send for approval"
            : kind === "replacement"
              ? "Raise the replacement"
              : "Close with no remedy"}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── withdraw (CMPL-007) ────────────────────────────────────────────────────────────

const withdrawSchema: z.ZodType<{ remark: string }, { remark: string }> = z.object({
  remark: z
    .string()
    .trim()
    .min(1, "Say why it is withdrawn.")
    .max(COMPLAINT_TEXT_MAX, "Keep it under 2000 characters."),
});

function WithdrawForm({
  complaint,
  onClose,
}: {
  complaint: Complaint;
  onClose: () => void;
}): React.JSX.Element {
  const withdraw = useWithdrawRemedy();
  const idempotency = useIdempotencyKey();
  const closeLater = useCloseLater(onClose);
  const [refusal, setRefusal] = useState<{ title: string; message: string } | null>(null);
  const form = useForm<{ remark: string }>({
    resolver: zodResolver(withdrawSchema),
    defaultValues: { remark: "" },
    mode: "onTouched",
  });
  const { errors } = useFormState({ control: form.control });
  const refund = complaint.remedy?.kind === "refund";

  const submit = useAsyncAction({
    action: ({ remark }: { remark: string }) => {
      const body = { remark: remark.trim() };
      return withdraw.mutateAsync({
        complaintId: complaint.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: complaint.id, ...body }),
      });
    },
    logger: log,
    fn: "handleWithdrawRemedy",
    dataId: "CMPL-007",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Remedy withdrawn", { description: "Choose the remedy again when ready." });
      closeLater();
    },
    onError: (error) => {
      const view = complaintRefusal(error);
      if (view.stale) {
        toast.error(view.title, { description: view.message });
        onClose();
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
        void form.handleSubmit((values) => submit.run(values))(event);
      }}
    >
      <DialogHeader>
        <DialogTitle>Withdraw the remedy?</DialogTitle>
        <DialogDescription>
          {refund
            ? "Its approval request closes, and the complaint goes back to QC to choose again."
            : "The complaint goes back to QC to choose again."}
        </DialogDescription>
      </DialogHeader>
      <DialogBody>
        <Field data-invalid={errors.remark ? true : undefined}>
          <FieldLabel htmlFor="remedy-withdraw-remark">Reason</FieldLabel>
          <Textarea
            id="remedy-withdraw-remark"
            rows={3}
            aria-invalid={errors.remark ? true : undefined}
            aria-describedby={errors.remark ? "remedy-withdraw-remark-error" : undefined}
            {...form.register("remark")}
          />
          <FieldError id="remedy-withdraw-remark-error">{errors.remark?.message}</FieldError>
        </Field>
        <Refusal refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it
        </DialogClose>
        <Button
          type="submit"
          variant="destructive"
          state={submit.state}
          loadingLabel="Withdrawing…"
          successLabel="Withdrawn"
          errorLabel="Not withdrawn"
        >
          Withdraw
        </Button>
      </DialogFooter>
    </form>
  );
}
