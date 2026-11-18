"use client";

import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
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
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  useRecordDeposit,
  useRelaxDeposit,
} from "@/features/dealer-applications/api/dealer-applications.mutations";
import type {
  DealerApplication,
  Deposit,
} from "@/features/dealer-applications/api/dealer-applications.schemas";
import {
  DEPOSIT_STATUS_BADGE,
  DEPOSIT_STATUS_LABELS,
} from "@/features/dealer-applications/lib/dealer-application-labels";
import { useUploadDocument } from "@/features/documents/api/documents.mutations";
import {
  DOCUMENT_CONTENT_TYPES,
  DOCUMENT_MAX_BYTES,
} from "@/features/documents/api/documents.schemas";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { readFieldErrors } from "@/lib/api/errors";
import { formatFullDate, formatInr, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { TextArea, TextField } from "./application-inputs";
import { refusalOf, RefusalNote, type Refusal } from "./dealer-application-refusals";

const log = createLogger({
  file: "features/dealer-applications/components/deposit-card.tsx",
  dataId: "CHNL-007",
});

/** The backend's `Money`: rupees, digits with at most two decimals. */
const RUPEES = /^\d{1,8}(\.\d{1,2})?$/;
const ACCEPT = [...DOCUMENT_CONTENT_TYPES, ".heic", ".heif"].join(",");

type DialogKind = "record" | "relax";

/**
 * CHNL-007 · The deposit a new dealer or distributor pays before approval (FS-071): the amount
 * set for the type, the amount due after any relaxation, the payment, and every payment and
 * relaxation in order. Staff with `record_deposit` record it with its pay slip; the roles the
 * company settings name lower or waive it. Approve waits until it is paid or waived.
 */
export function DepositCard({
  application,
}: {
  application: DealerApplication;
}): React.JSX.Element | null {
  const [dialog, setDialog] = useState<DialogKind | null>(null);
  const deposit = application.deposit;
  if (deposit === null) return null;
  const { recordDeposit, relaxDeposit } = application.can;
  const close = (): void => {
    setDialog(null);
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle level={3}>Deposit</CardTitle>
            <Badge variant={DEPOSIT_STATUS_BADGE[deposit.status]} dot>
              {DEPOSIT_STATUS_LABELS[deposit.status]}
            </Badge>
          </div>
          <CardDescription>{describe(deposit, application.partnerType)}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <dl className="grid gap-x-6 gap-y-4 sm:grid-cols-3">
          <Fact label="Set for the type">{formatInr(deposit.amountSet)}</Fact>
          <Fact label="Due">{formatInr(deposit.amountDue)}</Fact>
          <Fact label="Paid">
            {deposit.paidAmount === null ? "Not yet" : formatInr(deposit.paidAmount)}
            {deposit.paidOn === null ? null : (
              <span className="block text-xs text-muted-foreground">
                on {formatFullDate(deposit.paidOn)}
                {deposit.reference === null ? "" : ` · ${deposit.reference}`}
              </span>
            )}
          </Fact>
        </dl>
        {deposit.history.length === 0 ? null : (
          <ol aria-label="Deposit history" className="flex flex-col gap-2 text-sm">
            {deposit.history.map((entry, index) => (
              // Entries have no id; the backend sends them oldest first.
              <li key={index} className="flex flex-col gap-0.5 border-l-2 border-border pl-3">
                <span className="text-foreground">
                  {entry.kind === "payment"
                    ? `Paid ${formatInr(entry.amount)}${entry.paidOn === null ? "" : ` on ${formatFullDate(entry.paidOn)}`}`
                    : `Due lowered from ${formatInr(entry.fromDue)} to ${formatInr(entry.to)}`}
                </span>
                <span className="text-xs text-muted-foreground">
                  {[entry.by, formatFullDate(entry.at), entry.reference, entry.reason]
                    .filter((part) => part !== null && part !== "")
                    .join(" · ")}
                </span>
              </li>
            ))}
          </ol>
        )}
        {recordDeposit || relaxDeposit ? (
          <div className="flex flex-wrap gap-2">
            {recordDeposit ? (
              <Button
                onClick={() => {
                  setDialog("record");
                }}
              >
                Record the deposit
              </Button>
            ) : null}
            {relaxDeposit ? (
              <Button
                variant="outline"
                onClick={() => {
                  setDialog("relax");
                }}
              >
                Lower or waive it
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
        <DialogContent size="sm">
          {dialog === "record" ? (
            <RecordDepositForm application={application} deposit={deposit} onClose={close} />
          ) : null}
          {dialog === "relax" ? (
            <RelaxDepositForm application={application} deposit={deposit} onClose={close} />
          ) : null}
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function describe(deposit: Deposit, partnerType: DealerApplication["partnerType"]): string {
  switch (deposit.status) {
    case "pending":
      return `A new ${partnerType} pays this before the application can be approved.`;
    case "paid":
      return "Paid. The application can be approved.";
    case "waived":
      return "Lowered to nothing. The application can be approved.";
    case "not_required":
      return `No deposit is set for a new ${partnerType}.`;
  }
}

type RecordField = "amount" | "paid_on" | "reference" | "slip_id";

/**
 * Record the deposit: the amount (at least what is due), the day it was paid, a reference,
 * and the pay slip, which is uploaded first as a document and then named by the record. A
 * slip already uploaded on a failed try is reused, not uploaded twice.
 */
function RecordDepositForm({
  application,
  deposit,
  onClose,
}: {
  application: DealerApplication;
  deposit: Deposit;
  onClose: () => void;
}): React.JSX.Element {
  const record = useRecordDeposit();
  const upload = useUploadDocument();
  const idempotency = useIdempotencyKey();
  const uploadKey = useIdempotencyKey();
  const today = todayInIndia();
  const [amount, setAmount] = useState(deposit.amountDue);
  const [paidOn, setPaidOn] = useState(today);
  const [reference, setReference] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [slipId, setSlipId] = useState<string | null>(null);
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<Partial<Record<RecordField, string>>>({});
  const [refusal, setRefusal] = useState<Refusal | null>(null);

  const local: Partial<Record<RecordField, string>> = {};
  const trimmed = amount.trim();
  if (!RUPEES.test(trimmed) || Number(trimmed) <= 0) {
    local.amount = "Rupees above 0, like 50000 (at most two decimals).";
  } else if (Number(trimmed) < Number(deposit.amountDue)) {
    local.amount = `At least what is due, ${formatInr(deposit.amountDue)}.`;
  }
  if (paidOn === "" || paidOn > today) local.paid_on = "The day it was paid, not after today.";
  if (slipId === null) {
    if (file === null) local.slip_id = "Attach the pay slip.";
    else if (file.size > DOCUMENT_MAX_BYTES) local.slip_id = "The file is over 10 MB.";
  }
  const problems = { ...(shown ? local : {}), ...server };

  const save = useAsyncAction({
    action: async () => {
      let slip = slipId;
      if (slip === null && file !== null) {
        const uploaded = await upload.mutateAsync({
          recordType: "dealer_application",
          recordId: application.id,
          docType: "deposit_slip",
          name: null,
          file,
          idempotencyKey: uploadKey.keyFor({ file: file.name, size: file.size }),
        });
        slip = uploaded.id;
        setSlipId(slip);
      }
      const body = {
        amount: trimmed,
        paid_on: paidOn,
        reference: reference.trim() === "" ? null : reference.trim(),
        slip_id: slip ?? "",
      };
      return record.mutateAsync({
        applicationId: application.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleRecordDeposit",
    dataId: "CHNL-007",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Deposit recorded");
      onClose();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null) {
        const mapped: Partial<Record<RecordField, string>> = {};
        for (const key of ["amount", "paid_on", "reference", "slip_id"] as const) {
          const message = fields[key];
          if (message !== undefined) mapped[key] = `The backend refused it: ${message}.`;
        }
        if (Object.keys(mapped).length > 0) {
          setServer(mapped);
          return;
        }
      }
      const { refusal: next, stale } = refusalOf(error);
      if (stale) {
        toast.error(next.title, { description: next.message });
        onClose();
        return;
      }
      setRefusal(next);
    },
  });

  return (
    <form
      noValidate
      aria-label="Record the deposit"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServer({});
        setRefusal(null);
        if (Object.keys(local).length > 0) return;
        void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Record the deposit</DialogTitle>
        <DialogDescription>
          {formatInr(deposit.amountDue)} is due from {application.firmName}. The pay slip is kept
          with the application&apos;s documents.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <TextField
          id="deposit-amount"
          label="Amount paid, in rupees"
          inputMode="decimal"
          value={amount}
          error={problems.amount}
          onChange={setAmount}
        />
        <TextField
          id="deposit-paid-on"
          label="Paid on"
          type="date"
          max={today}
          value={paidOn}
          error={problems.paid_on}
          onChange={setPaidOn}
        />
        <TextField
          id="deposit-reference"
          label="Reference"
          optional
          maxLength={100}
          description="The UTR, cheque or receipt number."
          value={reference}
          error={problems.reference}
          onChange={setReference}
        />
        <Field data-invalid={problems.slip_id === undefined ? undefined : true}>
          <FieldLabel htmlFor="deposit-slip">Pay slip</FieldLabel>
          {slipId === null ? (
            <Input
              id="deposit-slip"
              type="file"
              accept={ACCEPT}
              aria-invalid={problems.slip_id === undefined ? undefined : true}
              aria-describedby={
                problems.slip_id === undefined ? "deposit-slip-hint" : "deposit-slip-error"
              }
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setServer(({ slip_id: _slip, ...rest }) => rest);
              }}
            />
          ) : (
            <p id="deposit-slip" className="text-sm text-foreground">
              Uploaded: {file?.name ?? "the pay slip"}.
            </p>
          )}
          {problems.slip_id === undefined ? (
            <FieldDescription id="deposit-slip-hint">A photo or PDF, up to 10 MB.</FieldDescription>
          ) : null}
          <FieldError id="deposit-slip-error">{problems.slip_id}</FieldError>
        </Field>
        <RefusalNote refusal={refusal} />
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={save.isBusy} />}>
          Cancel
        </DialogClose>
        <Button
          type="submit"
          state={save.state}
          loadingLabel="Recording…"
          successLabel="Recorded"
          errorLabel="Not recorded"
        >
          Record the deposit
        </Button>
      </DialogFooter>
    </form>
  );
}

type RelaxField = "amount_due" | "reason";

/** Lower the amount due, or waive it with 0, saying why. */
function RelaxDepositForm({
  application,
  deposit,
  onClose,
}: {
  application: DealerApplication;
  deposit: Deposit;
  onClose: () => void;
}): React.JSX.Element {
  const relax = useRelaxDeposit();
  const idempotency = useIdempotencyKey();
  const [amountDue, setAmountDue] = useState("0");
  const [reason, setReason] = useState("");
  const [shown, setShown] = useState(false);
  const [server, setServer] = useState<Partial<Record<RelaxField, string>>>({});
  const [refusal, setRefusal] = useState<Refusal | null>(null);

  const local: Partial<Record<RelaxField, string>> = {};
  const trimmed = amountDue.trim();
  if (!RUPEES.test(trimmed)) local.amount_due = "Rupees, like 25000; 0 waives it.";
  else if (Number(trimmed) >= Number(deposit.amountDue)) {
    local.amount_due = `Lower than what is due now, ${formatInr(deposit.amountDue)}.`;
  }
  if (reason.trim() === "") local.reason = "Say why it is lowered.";
  const problems = { ...(shown ? local : {}), ...server };

  const save = useAsyncAction({
    action: () => {
      const body = { amount_due: trimmed, reason: reason.trim() };
      return relax.mutateAsync({
        applicationId: application.id,
        body,
        idempotencyKey: idempotency.keyFor(body),
      });
    },
    logger: log,
    fn: "handleRelaxDeposit",
    dataId: "CHNL-007",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success(saved.deposit?.status === "waived" ? "Deposit waived" : "Deposit lowered");
      onClose();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null && (fields.amount_due !== undefined || fields.reason !== undefined)) {
        setServer({
          ...(fields.amount_due === undefined
            ? {}
            : { amount_due: `The backend refused it: ${fields.amount_due}.` }),
          ...(fields.reason === undefined ? {} : { reason: "Say why it is lowered." }),
        });
        return;
      }
      const { refusal: next, stale } = refusalOf(error);
      if (stale) {
        toast.error(next.title, { description: next.message });
        onClose();
        return;
      }
      setRefusal(next);
    },
  });

  return (
    <form
      noValidate
      aria-label="Lower or waive the deposit"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setServer({});
        setRefusal(null);
        if (Object.keys(local).length > 0) return;
        void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Lower or waive the deposit</DialogTitle>
        <DialogDescription>
          {formatInr(deposit.amountDue)} is due now. The reason is kept with the deposit.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <TextField
          id="deposit-new-due"
          label="New amount due, in rupees"
          inputMode="decimal"
          description="0 waives it."
          value={amountDue}
          error={problems.amount_due}
          onChange={setAmountDue}
        />
        <TextArea
          id="deposit-reason"
          label="Why"
          value={reason}
          error={problems.reason}
          onChange={setReason}
        />
        <RefusalNote refusal={refusal} />
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
          {trimmed === "0" ? "Waive it" : "Lower it"}
        </Button>
      </DialogFooter>
    </form>
  );
}

function Fact({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}): React.JSX.Element {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm wrap-break-word text-foreground tabular-nums">{children}</dd>
    </div>
  );
}
