"use client";

import { Cancel01Icon } from "@hugeicons/core-free-icons";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useRecordPayment } from "@/features/payments/api/payments.mutations";
import {
  MODES_WITH_REFERENCE,
  PAYMENT_MODES,
  type PaymentMode,
} from "@/features/payments/api/payments.schemas";
import {
  PAYMENT_MODE_LABELS,
  fromPaise,
  rupeesProblem,
  toPaise,
} from "@/features/payments/lib/payment-labels";
import { PartnerSearchPicker } from "@/features/schemes/components/record-pickers";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatInr, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

import { AllocationEditor, type Allocations } from "./allocation-editor";

const log = createLogger({
  file: "features/payments/components/record-payment-form.tsx",
  dataId: "ACCT-002",
});

const MODE_ITEMS = PAYMENT_MODES.map((value) => ({ value, label: PAYMENT_MODE_LABELS[value] }));

/** Opened from an order: its dealer (or none, a direct sale) and what it still owes. */
export interface PaymentStart {
  readonly partner: { readonly id: string; readonly name: string } | null;
  readonly order: {
    readonly id: string;
    readonly orderNo: string | null;
    readonly balance: string;
  };
}

const FIELDS = ["mode", "ref_no", "received_on", "amount", "remark"] as const;
type Field = (typeof FIELDS)[number];

/**
 * ACCT-002 · Record money received. From an order, its dealer is set and the order's balance is
 * offered; from the Receipts page, a dealer is chosen. A dealer's receipt is spread over its
 * orders, and what isn't spread stays on its account; a direct order's goes on it in full.
 */
export function RecordPaymentForm({
  start,
  onClose,
}: {
  start: PaymentStart | null;
  onClose: () => void;
}): React.JSX.Element {
  const record = useRecordPayment();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const today = todayInIndia();
  const direct = start !== null && start.partner === null;
  const [partner, setPartner] = useState(start?.partner ?? null);
  const [mode, setMode] = useState<PaymentMode>("neft");
  const [ref, setRef] = useState("");
  const [receivedOn, setReceivedOn] = useState(today);
  const [amount, setAmount] = useState(
    start !== null && Number(start.order.balance) > 0 ? start.order.balance : "",
  );
  const [short, setShort] = useState(false);
  const [remark, setRemark] = useState("");
  const [allocations, setAllocations] = useState<Allocations>(
    start !== null && start.partner !== null && Number(start.order.balance) > 0
      ? { [start.order.id]: start.order.balance }
      : {},
  );
  const [shown, setShown] = useState(false);
  const [serverFields, setServerFields] = useState<Partial<Record<Field, string>>>({});
  const [allocationProblems, setAllocationProblems] = useState<Readonly<Record<string, string>>>(
    {},
  );
  const [refusal, setRefusal] = useState<string | null>(null);

  const amountPaise = toPaise(amount);
  const rows = Object.entries(allocations).filter(([, value]) => value.trim() !== "");
  const allocatedPaise = direct
    ? amountPaise
    : rows.reduce((sum, [, value]) => sum + toPaise(value), 0);
  const left = amountPaise - allocatedPaise;
  const needsRef = MODES_WITH_REFERENCE.includes(mode);
  const problems: Record<Field, string | null> = {
    mode: null,
    ref_no: needsRef && ref.trim() === "" ? "The UTR, UPI or cheque number." : null,
    received_on: !/^\d{4}-\d{2}-\d{2}$/.test(receivedOn)
      ? "Choose the day it came in."
      : receivedOn > today
        ? "Not in the future."
        : null,
    amount: rupeesProblem(amount, true) ?? (amountPaise <= 0 ? "More than 0." : null),
    remark: null,
  };
  const spreadProblem =
    left < 0
      ? "The orders add up to more than the amount."
      : rows.some(([, value]) => rupeesProblem(value, false) !== null)
        ? "Fix the amounts on the orders."
        : null;
  const problemOf = (field: Field): string | null =>
    serverFields[field] ?? (shown ? problems[field] : null);
  const ready =
    partner !== null || direct
      ? Object.values(problems).every((problem) => problem === null) && spreadProblem === null
      : false;

  const submit = useAsyncAction({
    action: () => {
      const body = {
        partner_id: partner?.id ?? null,
        mode,
        ref_no: ref.trim() === "" ? null : ref.trim(),
        received_on: receivedOn,
        amount: amount.trim(),
        is_short_payment: short,
        remark: remark.trim() === "" ? null : remark.trim(),
        allocations: direct
          ? [{ sales_order_id: start.order.id, amount: amount.trim() }]
          : rows.map(([orderId, value]) => ({ sales_order_id: orderId, amount: value.trim() })),
      };
      return record.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleRecordPayment",
    dataId: "ACCT-002",
    onSuccess: (payment) => {
      idempotency.reset();
      toast.success("Payment recorded", {
        description:
          Number(payment.unallocated) > 0
            ? `${formatInr(payment.unallocated, { paise: true })} stays on ${payment.partner?.name ?? "the dealer"}'s account.`
            : `${formatInr(payment.amount, { paise: true })} put on the orders.`,
      });
      closeSoon();
    },
    onError: (error) => {
      const fields = readFieldErrors(error) ?? {};
      const own: Partial<Record<Field, string>> = {};
      const onOrders: Record<string, string> = {};
      for (const [path, reason] of Object.entries(fields)) {
        const row = /^allocations\[(\d+)\]/.exec(path);
        const orderId = row?.[1] === undefined ? undefined : rows[Number(row[1])]?.[0];
        if (orderId !== undefined) onOrders[orderId] = reason;
        else {
          const field = FIELDS.find((name) => name === path);
          if (field !== undefined) own[field] = reason;
        }
      }
      setServerFields(own);
      setAllocationProblems(onOrders);
      if (isApiError(error)) {
        if (error.code === "duplicate_reference") {
          setServerFields({ ref_no: "Already recorded for this dealer." });
          return;
        }
        if (error.code === "over_allocated" || error.code === "must_allocate") {
          setRefusal(
            error.code === "must_allocate"
              ? "A direct order's payment goes on it in full."
              : "The orders add up to more than the amount.",
          );
          return;
        }
        if (error.code === "order_not_payable") {
          setRefusal("One of the orders can't be paid now (a draft or cancelled). Take it out.");
          return;
        }
        if (error.code === "partner_mismatch") {
          setRefusal("One of the orders belongs to another dealer.");
          return;
        }
      }
      if (Object.keys(own).length === 0 && Object.keys(onOrders).length === 0) {
        setRefusal(toUserFacingError(error).title);
      }
    },
  });

  const clear = (field: Field): void => {
    setServerFields(({ [field]: _cleared, ...rest }) => rest);
  };

  return (
    <form
      noValidate
      aria-label="Record a payment"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (!ready) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Record a payment</DialogTitle>
        <DialogDescription>
          {start === null
            ? "Money received from a dealer, spread over its orders. What isn't spread stays on its account."
            : direct
              ? `A direct sale: the payment goes on ${start.order.orderNo ?? "this order"} in full.`
              : `From ${start.partner?.name ?? "the dealer"}, starting with ${start.order.orderNo ?? "this order"}.`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {start === null ? (
          <Field data-invalid={shown && partner === null ? true : undefined}>
            <FieldLabel htmlFor="payment-dealer">Dealer</FieldLabel>
            {partner === null ? (
              <PartnerSearchPicker
                id="payment-dealer"
                placeholder="Search the dealer who paid"
                aria-describedby={shown ? "payment-dealer-error" : undefined}
                onPick={(picked) => {
                  setPartner({ id: picked.id, name: picked.name });
                  setAllocations({});
                }}
              />
            ) : (
              <div className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm">
                <span className="text-foreground">{partner.name}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Choose another dealer than ${partner.name}`}
                  onClick={() => {
                    setPartner(null);
                    setAllocations({});
                  }}
                >
                  <Icon icon={Cancel01Icon} />
                </Button>
              </div>
            )}
            {shown && partner === null ? (
              <FieldError id="payment-dealer-error">Choose the dealer.</FieldError>
            ) : null}
          </Field>
        ) : null}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="payment-mode">Mode</FieldLabel>
            <Select
              items={MODE_ITEMS}
              value={mode}
              onValueChange={(next) => {
                const chosen = PAYMENT_MODES.find((value) => value === next);
                if (chosen !== undefined) setMode(chosen);
                clear("ref_no");
              }}
            >
              <SelectTrigger id="payment-mode" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODE_ITEMS.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field data-invalid={problemOf("ref_no") === null ? undefined : true}>
            <FieldLabel htmlFor="payment-ref">
              Reference
              {needsRef ? null : (
                <span className="font-normal text-muted-foreground">(optional)</span>
              )}
            </FieldLabel>
            <Input
              id="payment-ref"
              autoComplete="off"
              maxLength={80}
              value={ref}
              placeholder={
                mode === "cheque" ? "Cheque number" : mode === "cash" ? "" : "UTR or UPI reference"
              }
              aria-invalid={problemOf("ref_no") === null ? undefined : true}
              aria-describedby={problemOf("ref_no") === null ? undefined : "payment-ref-error"}
              onChange={(event) => {
                setRef(event.target.value);
                clear("ref_no");
              }}
            />
            {problemOf("ref_no") === null ? null : (
              <FieldError id="payment-ref-error">{problemOf("ref_no")}</FieldError>
            )}
          </Field>
          <Field data-invalid={problemOf("received_on") === null ? undefined : true}>
            <FieldLabel htmlFor="payment-on">Received on</FieldLabel>
            <Input
              id="payment-on"
              type="date"
              max={today}
              value={receivedOn}
              aria-invalid={problemOf("received_on") === null ? undefined : true}
              aria-describedby={problemOf("received_on") === null ? undefined : "payment-on-error"}
              onChange={(event) => {
                setReceivedOn(event.target.value);
                clear("received_on");
              }}
            />
            {problemOf("received_on") === null ? null : (
              <FieldError id="payment-on-error">{problemOf("received_on")}</FieldError>
            )}
          </Field>
          <Field data-invalid={problemOf("amount") === null ? undefined : true}>
            <FieldLabel htmlFor="payment-amount">Amount</FieldLabel>
            <InputGroup>
              <InputGroupAddon>₹</InputGroupAddon>
              <InputGroupInput
                id="payment-amount"
                inputMode="decimal"
                autoComplete="off"
                className="tabular-nums"
                value={amount}
                aria-invalid={problemOf("amount") === null ? undefined : true}
                aria-describedby={problemOf("amount") === null ? undefined : "payment-amount-error"}
                onChange={(event) => {
                  setAmount(event.target.value);
                  clear("amount");
                }}
              />
            </InputGroup>
            {problemOf("amount") === null ? null : (
              <FieldError id="payment-amount-error">{problemOf("amount")}</FieldError>
            )}
          </Field>
        </div>

        {direct ? null : partner === null ? null : (
          <section aria-label="Spread over the orders" className="flex flex-col gap-2">
            <h3 className="text-sm font-medium text-foreground">Put it on the orders</h3>
            <AllocationEditor
              partnerId={partner.id}
              value={allocations}
              problems={allocationProblems}
              onChange={(next) => {
                setAllocations(next);
                setAllocationProblems({});
              }}
            />
          </section>
        )}

        {direct ? null : (
          <dl
            aria-label="What the amount covers"
            className="grid grid-cols-2 gap-x-4 gap-y-1 rounded-lg bg-muted p-3 text-sm"
          >
            <dt className="text-muted-foreground">On the orders</dt>
            <dd className="text-right text-foreground tabular-nums">
              {formatInr(fromPaise(allocatedPaise), { paise: true })}
            </dd>
            <dt className="text-muted-foreground">Stays on the dealer&apos;s account</dt>
            <dd
              className={
                left < 0
                  ? "text-right text-danger tabular-nums"
                  : "text-right text-foreground tabular-nums"
              }
            >
              {formatInr(fromPaise(Math.max(0, left)), { paise: true })}
            </dd>
          </dl>
        )}
        {shown && spreadProblem !== null ? (
          <p role="alert" className="text-sm text-danger">
            {spreadProblem}
          </p>
        ) : null}

        <div className="flex items-start gap-2">
          <Checkbox
            id="payment-short"
            checked={short}
            aria-describedby="payment-short-hint"
            onCheckedChange={(checked) => {
              setShort(checked);
            }}
          />
          <div className="flex flex-col gap-0.5">
            <Label htmlFor="payment-short">A short payment</Label>
            <FieldDescription id="payment-short-hint">
              Recorded and shown; it changes no figure.
            </FieldDescription>
          </div>
        </div>
        <Field>
          <FieldLabel htmlFor="payment-remark">
            Remark <span className="font-normal text-muted-foreground">(internal, optional)</span>
          </FieldLabel>
          <Textarea
            id="payment-remark"
            rows={2}
            maxLength={500}
            value={remark}
            onChange={(event) => {
              setRemark(event.target.value);
            }}
          />
        </Field>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
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
          loadingLabel="Recording…"
          successLabel="Recorded"
          errorLabel="Not recorded"
        >
          Record payment
        </Button>
      </DialogFooter>
    </form>
  );
}
