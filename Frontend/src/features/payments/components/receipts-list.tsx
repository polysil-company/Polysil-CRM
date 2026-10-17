"use client";

import { Add01Icon, Cancel01Icon, RupeeIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { EmptyState } from "@/components/patterns/empty-state";
import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
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
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Icon } from "@/components/ui/icon";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAllocatePayment, useVoidPayment } from "@/features/payments/api/payments.mutations";
import { paymentListQueryOptions } from "@/features/payments/api/payments.queries";
import type { Payment } from "@/features/payments/api/payments.schemas";
import {
  PAYMENT_MODE_LABELS,
  fromPaise,
  rupeesProblem,
  toPaise,
} from "@/features/payments/lib/payment-labels";
import { PartnerSearchPicker } from "@/features/schemes/components/record-pickers";
import { useCan } from "@/features/session/hooks/use-session";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatCount, formatInr } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import { AllocationEditor, type Allocations } from "./allocation-editor";
import { RecordPaymentForm } from "./record-payment-form";

const log = createLogger({
  file: "features/payments/components/receipts-list.tsx",
  dataId: "ACCT-003",
});

type Opened =
  | { readonly kind: "record" }
  | { readonly kind: "void"; readonly payment: Payment }
  | { readonly kind: "allocate"; readonly payment: Payment };

/**
 * ACCT-003 · Receipts, newest first: who paid, how, and where the money went. Accounts records
 * a payment, spreads what is left of a dealer's receipt, and voids a mistake (it is re-entered,
 * never edited). A dealer filter and voided receipts on request.
 */
export function ReceiptsList(): React.JSX.Element {
  const canRecord = useCan("payments", "create");
  const canEdit = useCan("payments", "edit");
  const [partner, setPartner] = useState<{ id: string; name: string } | null>(null);
  const [withVoided, setWithVoided] = useState(false);
  const [opened, setOpened] = useState<Opened | null>(null);
  const query = useInfiniteQuery(
    paymentListQueryOptions({
      partnerId: partner?.id ?? null,
      orderId: null,
      includeVoided: withVoided,
    }),
  );
  const rows = query.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field className="sm:w-72">
            <FieldLabel htmlFor="receipts-dealer">Dealer</FieldLabel>
            {partner === null ? (
              <PartnerSearchPicker
                id="receipts-dealer"
                placeholder="Every dealer"
                onPick={(picked) => {
                  setPartner({ id: picked.id, name: picked.name });
                }}
              />
            ) : (
              <div className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2 text-sm">
                <span className="text-foreground">{partner.name}</span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Show every dealer, not only ${partner.name}`}
                  onClick={() => {
                    setPartner(null);
                  }}
                >
                  <Icon icon={Cancel01Icon} />
                </Button>
              </div>
            )}
          </Field>
          <div className="flex items-center gap-2 sm:pb-2">
            <Checkbox
              id="receipts-voided"
              checked={withVoided}
              onCheckedChange={(checked) => {
                setWithVoided(checked);
              }}
            />
            <Label htmlFor="receipts-voided">Show voided</Label>
          </div>
        </div>
        {canRecord ? (
          <Button
            onClick={() => {
              setOpened({ kind: "record" });
            }}
          >
            <Icon icon={Add01Icon} />
            Record payment
          </Button>
        ) : null}
      </div>

      {query.status === "pending" ? (
        <div aria-busy="true" aria-label="Loading receipts" className="flex flex-col gap-2">
          {[0, 1, 2].map((row) => (
            <Skeleton key={row} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      ) : query.status === "error" ? (
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={RupeeIcon}
          title={partner === null ? "No receipts yet" : `No receipts from ${partner.name}`}
          description="Each payment received is recorded here, with the orders it went on."
          className="rounded-xl border border-dashed border-border"
        />
      ) : (
        <div className="flex flex-col gap-3">
          <p aria-live="polite" className="text-sm text-muted-foreground">
            {formatCount(rows.length)}
            {query.hasNextPage ? "+" : ""} {rows.length === 1 ? "receipt" : "receipts"}, newest
            first.
          </p>
          <ul aria-label="Receipts" className="flex flex-col gap-2">
            {rows.map((payment) => (
              <ReceiptRow
                key={payment.id}
                payment={payment}
                canEdit={canEdit}
                onOpen={(kind) => {
                  setOpened({ kind, payment });
                }}
              />
            ))}
          </ul>
          {query.hasNextPage ? (
            <Button
              variant="outline"
              className="self-center"
              disabled={query.isFetchingNextPage}
              onClick={() => {
                void query.fetchNextPage();
              }}
            >
              {query.isFetchingNextPage ? "Loading…" : "Show more"}
            </Button>
          ) : null}
        </div>
      )}

      <Dialog
        open={opened !== null}
        onOpenChange={(open) => {
          if (!open) setOpened(null);
        }}
      >
        <DialogContent size={opened?.kind === "void" ? "sm" : "lg"}>
          {opened?.kind === "record" ? (
            <RecordPaymentForm
              start={null}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : null}
          {opened?.kind === "void" ? (
            <VoidForm
              payment={opened.payment}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : null}
          {opened?.kind === "allocate" ? (
            <AllocateForm
              payment={opened.payment}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ReceiptRow({
  payment,
  canEdit,
  onOpen,
}: {
  payment: Payment;
  canEdit: boolean;
  onOpen: (kind: "void" | "allocate") => void;
}): React.JSX.Element {
  const voided = payment.voided !== null;
  const who = payment.partner?.name ?? "A direct sale";
  const left = Number(payment.unallocated) > 0;
  return (
    <li
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-border bg-card p-3 sm:p-4",
        voided && "opacity-70",
      )}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <span className="flex min-w-0 flex-col gap-1">
          <span className="flex flex-wrap items-center gap-2 text-sm font-semibold text-foreground">
            <span className={cn(voided && "line-through")}>{who}</span>
            {voided ? (
              <Badge variant="neutral" size="sm">
                Voided
              </Badge>
            ) : null}
            {payment.shortPayment ? (
              <Badge variant="warning" size="sm">
                Short payment
              </Badge>
            ) : null}
          </span>
          <span className="text-xs text-muted-foreground">
            {PAYMENT_MODE_LABELS[payment.mode]}
            {payment.refNo === null ? "" : ` · ${payment.refNo}`} · received{" "}
            {formatBusinessDay(payment.receivedOn)} · entered by{" "}
            {payment.enteredBy?.name ?? "someone"} <RelativeDate value={payment.enteredAt} />
          </span>
          {payment.voided === null ? null : (
            <span className="text-xs text-muted-foreground">
              Voided by {payment.voided.by?.name ?? "someone"}
              {payment.voided.reason === null ? "" : `: ${payment.voided.reason}`}
            </span>
          )}
          {payment.remark === null ? null : (
            <span className="text-xs text-muted-foreground">{payment.remark}</span>
          )}
        </span>
        <span className="flex flex-col gap-0.5 sm:items-end">
          <span
            className={cn(
              "text-base font-semibold text-foreground tabular-nums",
              voided && "line-through",
            )}
          >
            {formatInr(payment.amount, { paise: true })}
          </span>
          {left && !voided ? (
            <span className="text-xs text-muted-foreground tabular-nums">
              {formatInr(payment.unallocated, { paise: true })} on account
            </span>
          ) : null}
        </span>
      </div>
      {payment.allocations.length === 0 ? null : (
        <ul
          aria-label={`Where ${who}'s payment went`}
          className="flex flex-wrap gap-x-4 gap-y-1 text-sm"
        >
          {payment.allocations.map((allocation) => (
            <li key={allocation.order.id} className="tabular-nums">
              <Link
                href={`/sales-orders/${allocation.order.id}`}
                className="font-mono text-primary-text underline-offset-4 hover:underline"
              >
                {allocation.order.orderNo ?? "Order"}
              </Link>{" "}
              {formatInr(allocation.amount, { paise: true })}
            </li>
          ))}
        </ul>
      )}
      {canEdit && !voided ? (
        <div className="flex flex-wrap gap-2">
          {left && payment.partner !== null ? (
            <Button
              size="sm"
              variant="outline"
              aria-label={`Spread what is left of ${who}'s payment`}
              onClick={() => {
                onOpen("allocate");
              }}
            >
              Put the rest on orders
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            aria-label={`Void ${who}'s payment of ${formatInr(payment.amount, { paise: true })}`}
            onClick={() => {
              onOpen("void");
            }}
          >
            Void
          </Button>
        </div>
      ) : null}
    </li>
  );
}

function VoidForm({
  payment,
  onClose,
}: {
  payment: Payment;
  onClose: () => void;
}): React.JSX.Element {
  const voidIt = useVoidPayment();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [reason, setReason] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const problem = reason.trim() === "" ? "Say why, for the record." : null;

  const submit = useAsyncAction({
    action: () =>
      voidIt.mutateAsync({
        paymentId: payment.id,
        body: { reason: reason.trim() },
        idempotencyKey: idempotency.keyFor({ id: payment.id, reason: reason.trim() }),
      }),
    logger: log,
    fn: "handleVoidPayment",
    dataId: "ACCT-003",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Payment voided", { description: "Enter it again if it was wrong." });
      closeSoon();
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.code === "already_void"
          ? "It was already voided."
          : toUserFacingError(error).title,
      );
    },
  });

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (problem !== null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Void this payment?</DialogTitle>
        <DialogDescription>
          {payment.partner?.name ?? "A direct sale"} · {formatInr(payment.amount, { paise: true })}.
          It comes off every order it went on; enter it again if it was wrong.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        <Field data-invalid={shown && problem !== null ? true : undefined}>
          <FieldLabel htmlFor="void-reason">Why</FieldLabel>
          <Textarea
            id="void-reason"
            rows={2}
            maxLength={300}
            value={reason}
            aria-invalid={shown && problem !== null ? true : undefined}
            aria-describedby={shown && problem !== null ? "void-reason-error" : undefined}
            onChange={(event) => {
              setReason(event.target.value);
            }}
          />
          {shown && problem !== null ? (
            <FieldError id="void-reason-error">{problem}</FieldError>
          ) : null}
        </Field>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Keep it
        </DialogClose>
        <Button
          type="submit"
          variant="destructive"
          state={submit.state}
          loadingLabel="Voiding…"
          successLabel="Voided"
          errorLabel="Not voided"
        >
          Void payment
        </Button>
      </DialogFooter>
    </form>
  );
}

function AllocateForm({
  payment,
  onClose,
}: {
  payment: Payment;
  onClose: () => void;
}): React.JSX.Element {
  const allocate = useAllocatePayment();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [allocations, setAllocations] = useState<Allocations>({});
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const rows = Object.entries(allocations).filter(([, value]) => value.trim() !== "");
  const spread = rows.reduce((sum, [, value]) => sum + toPaise(value), 0);
  const left = toPaise(payment.unallocated) - spread;
  const problem =
    rows.length === 0
      ? "Put an amount on at least one order."
      : rows.some(([, value]) => rupeesProblem(value, false) !== null)
        ? "Fix the amounts on the orders."
        : left < 0
          ? `More than the ${formatInr(payment.unallocated, { paise: true })} left.`
          : null;

  const submit = useAsyncAction({
    action: () => {
      const body = {
        allocations: rows.map(([id, value]) => ({ sales_order_id: id, amount: value.trim() })),
      };
      return allocate.mutateAsync({
        paymentId: payment.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: payment.id, ...body }),
      });
    },
    logger: log,
    fn: "handleAllocatePayment",
    dataId: "ACCT-003",
    onSuccess: (saved) => {
      idempotency.reset();
      toast.success("Put on the orders", {
        description:
          Number(saved.unallocated) > 0
            ? `${formatInr(saved.unallocated, { paise: true })} still on account.`
            : "Nothing left on account.",
      });
      closeSoon();
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.code === "over_allocated"
          ? "More than what is left of the receipt."
          : isApiError(error) && error.code === "order_not_payable"
            ? "One of the orders can't be paid now."
            : toUserFacingError(error).title,
      );
    },
  });

  return (
    <form
      noValidate
      aria-label="Put the rest on orders"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (problem !== null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Put the rest on orders</DialogTitle>
        <DialogDescription>
          {formatInr(payment.unallocated, { paise: true })} of{" "}
          {payment.partner?.name ?? "the dealer"}&apos;s payment is on account.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        {payment.partner === null ? null : (
          <AllocationEditor
            partnerId={payment.partner.id}
            value={allocations}
            problems={{}}
            onChange={setAllocations}
          />
        )}
        <p
          className={cn("text-sm tabular-nums", left < 0 ? "text-danger" : "text-muted-foreground")}
        >
          {formatInr(fromPaise(Math.max(0, left)), { paise: true })} would stay on account.
        </p>
        {shown && problem !== null ? (
          <p role="alert" className="text-sm text-danger">
            {problem}
          </p>
        ) : null}
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
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Put on the orders
        </Button>
      </DialogFooter>
    </form>
  );
}
