"use client";

import { Add01Icon, Delete02Icon, RupeeIcon } from "@hugeicons/core-free-icons";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Notice } from "@/components/patterns/notice";
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
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import type { Order } from "@/features/orders/api/orders.schemas";
import { useSavePaymentSchedule } from "@/features/payments/api/payments.mutations";
import {
  MAX_INSTALMENTS,
  type OrderPayments as Payments,
} from "@/features/payments/api/payments.schemas";
import {
  ORDER_PAYMENT_STATUS_BADGE,
  ORDER_PAYMENT_STATUS_LABELS,
  PAYMENT_MODE_LABELS,
  fromPaise,
  rupeesProblem,
  toPaise,
} from "@/features/payments/lib/payment-labels";
import { useCan } from "@/features/session/hooks/use-session";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatInr, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { cn } from "@/lib/utils";

import { RecordPaymentForm } from "./record-payment-form";

const log = createLogger({
  file: "features/payments/components/order-payments.tsx",
  dataId: "ACCT-004",
});

const TITLE_ID = "order-payments-title";

/**
 * ACCT-004 · An order's payments: what it owes after benefits, what came in, the balance, the
 * instalment plan and the receipts. Hidden when the reader may not see payments (a field
 * officer: `payments` is null) and on a draft. Accounts records a payment and plans instalments.
 */
export function OrderPaymentsCard({ order }: { order: Order }): React.JSX.Element | null {
  const canRecord = useCan("payments", "create");
  const canPlan = useCan("payments", "edit");
  const [opened, setOpened] = useState<"record" | "plan" | null>(null);
  const payments = order.payments;
  if (payments === null || order.status === "draft") return null;
  const payable = payments.status !== "not_applicable";
  const money = (value: string): string => formatInr(value, { paise: true });

  return (
    <section aria-labelledby={TITLE_ID}>
      <Card>
        <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <CardTitle level={3} id={TITLE_ID} className="flex items-center gap-2">
              <Icon icon={RupeeIcon} size="sm" className="text-muted-foreground" />
              Payments
            </CardTitle>
            <CardDescription>
              What is owed after scheme and reward benefits, and what has come in.
            </CardDescription>
          </div>
          <Badge variant={ORDER_PAYMENT_STATUS_BADGE[payments.status]} dot>
            {ORDER_PAYMENT_STATUS_LABELS[payments.status]}
          </Badge>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <dl aria-label="Payment figures" className="grid grid-cols-3 gap-3 text-sm">
            {[
              { term: "To pay", value: payments.payable },
              { term: "Received", value: payments.received },
              { term: "Balance", value: payments.balance, strong: true },
            ].map((row) => (
              <div key={row.term} className="flex flex-col gap-0.5 rounded-lg bg-muted p-3">
                <dt className="text-xs text-muted-foreground">{row.term}</dt>
                <dd
                  className={cn(
                    "text-foreground tabular-nums",
                    row.strong === true ? "text-base font-semibold" : "font-medium",
                  )}
                >
                  {money(row.value)}
                </dd>
              </div>
            ))}
          </dl>
          {payments.overdue ? (
            <Notice tone="warning">
              <p className="font-medium">{money(payments.overdueAmount)} overdue</p>
              <p>An instalment due before today isn&apos;t covered yet.</p>
            </Notice>
          ) : null}

          <Schedule payments={payments} />
          <Receipts payments={payments} />

          {payable && (canRecord || canPlan) ? (
            <div className="flex flex-wrap gap-2">
              {canRecord ? (
                <Button
                  onClick={() => {
                    setOpened("record");
                  }}
                >
                  Record payment
                </Button>
              ) : null}
              {canPlan ? (
                <Button
                  variant="outline"
                  onClick={() => {
                    setOpened("plan");
                  }}
                >
                  {payments.schedule.length === 0 ? "Plan instalments" : "Change instalments"}
                </Button>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Dialog
        open={opened !== null}
        onOpenChange={(open) => {
          if (!open) setOpened(null);
        }}
      >
        <DialogContent size={opened === "record" ? "lg" : "md"}>
          {opened === "record" ? (
            <RecordPaymentForm
              start={{
                partner:
                  order.partner === null
                    ? null
                    : { id: order.partner.id, name: order.partner.name },
                order: { id: order.id, orderNo: order.orderNo, balance: payments.balance },
              }}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : null}
          {opened === "plan" ? (
            <ScheduleForm
              order={order}
              payments={payments}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : null}
        </DialogContent>
      </Dialog>
    </section>
  );
}

function Schedule({ payments }: { payments: Payments }): React.JSX.Element | null {
  if (payments.schedule.length === 0) return null;
  const today = todayInIndia();
  return (
    <section aria-label="Instalments" className="flex flex-col gap-2">
      <h4 className="text-xs font-medium text-muted-foreground">Instalments</h4>
      <ul className="flex flex-col divide-y divide-border">
        {payments.schedule.map((row) => {
          const late = !row.covered && row.dueOn < today;
          return (
            <li key={row.seq} className="flex items-center justify-between gap-3 py-2">
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-sm text-foreground">
                  {row.note ?? `Instalment ${String(row.seq)}`}
                </span>
                <span className="text-xs text-muted-foreground">
                  Due {formatBusinessDay(row.dueOn)}
                </span>
              </span>
              <span className="flex items-center gap-2">
                <span className="text-sm text-foreground tabular-nums">
                  {formatInr(row.amount, { paise: true })}
                </span>
                <Badge variant={row.covered ? "success" : late ? "danger" : "neutral"} size="sm">
                  {row.covered ? "Covered" : late ? "Overdue" : "Due"}
                </Badge>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Receipts({ payments }: { payments: Payments }): React.JSX.Element {
  return (
    <section aria-label="Receipts" className="flex flex-col gap-2">
      <h4 className="text-xs font-medium text-muted-foreground">Receipts</h4>
      {payments.receipts.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing received yet.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-border">
          {payments.receipts.map((receipt) => (
            <li
              key={`${receipt.paymentId}-${receipt.receivedOn}`}
              className="flex items-center justify-between gap-3 py-2"
            >
              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="flex flex-wrap items-center gap-2 text-sm text-foreground">
                  {PAYMENT_MODE_LABELS[receipt.mode]}
                  {receipt.shortPayment ? (
                    <Badge variant="warning" size="sm">
                      Short payment
                    </Badge>
                  ) : null}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatBusinessDay(receipt.receivedOn)}
                  {receipt.refNo === null ? "" : ` · ${receipt.refNo}`}
                </span>
              </span>
              <span className="text-sm text-foreground tabular-nums">
                {formatInr(receipt.amount, { paise: true })}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

interface Row {
  readonly key: number;
  readonly dueOn: string;
  readonly amount: string;
  readonly note: string;
}

/** ACCT-004 · Replace the plan: up to five instalments, adding up to no more than the payable. */
function ScheduleForm({
  order,
  payments,
  onClose,
}: {
  order: Order;
  payments: Payments;
  onClose: () => void;
}): React.JSX.Element {
  const save = useSavePaymentSchedule();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const [rows, setRows] = useState<readonly Row[]>(
    payments.schedule.length === 0
      ? [{ key: 1, dueOn: todayInIndia(), amount: payments.payable, note: "" }]
      : payments.schedule.map((row) => ({
          key: row.seq,
          dueOn: row.dueOn,
          amount: row.amount,
          note: row.note ?? "",
        })),
  );
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const total = rows.reduce((sum, row) => sum + toPaise(row.amount), 0);
  const payable = toPaise(payments.payable);
  const rowProblems = rows.map((row) => ({
    dueOn: /^\d{4}-\d{2}-\d{2}$/.test(row.dueOn) ? null : "A date.",
    amount: rupeesProblem(row.amount, true) ?? (toPaise(row.amount) <= 0 ? "More than 0." : null),
  }));
  const overProblem =
    total > payable
      ? `They add up to more than the payable, ${formatInr(payments.payable, { paise: true })}.`
      : null;
  const valid =
    overProblem === null && rowProblems.every((row) => row.dueOn === null && row.amount === null);
  const nextKey = rows.reduce((most, row) => Math.max(most, row.key), 0) + 1;

  const submit = useAsyncAction({
    action: () => {
      const body = {
        instalments: rows.map((row) => ({
          due_on: row.dueOn,
          amount: row.amount.trim(),
          note: row.note.trim() === "" ? null : row.note.trim(),
        })),
      };
      return save.mutateAsync({
        orderId: order.id,
        body,
        idempotencyKey: idempotency.keyFor({ orderId: order.id, ...body }),
      });
    },
    logger: log,
    fn: "handleSavePaymentSchedule",
    dataId: "ACCT-004",
    onSuccess: () => {
      idempotency.reset();
      toast.success(rows.length === 0 ? "Instalments cleared" : "Instalments saved", {
        description: order.orderNo ?? undefined,
      });
      closeSoon();
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.code === "schedule_over_payable"
          ? "They add up to more than the payable."
          : isApiError(error) && error.code === "order_not_payable"
            ? "This order can't be paid now."
            : toUserFacingError(error).title,
      );
    },
  });

  const update = (key: number, change: Partial<Row>): void => {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...change } : row)));
  };

  return (
    <form
      noValidate
      aria-label="Instalments"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (!valid) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Instalments for {order.orderNo ?? "this order"}</DialogTitle>
        <DialogDescription>
          Up to {String(MAX_INSTALMENTS)}, adding up to no more than{" "}
          {formatInr(payments.payable, { paise: true })}. Saving replaces the plan.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">No instalments: saving clears the plan.</p>
        ) : (
          <ul aria-label="Planned instalments" className="flex flex-col gap-3">
            {rows.map((row, index) => {
              const problem = shown ? rowProblems[index] : undefined;
              const label = `Instalment ${String(index + 1)}`;
              return (
                <li
                  key={row.key}
                  className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-[1fr_1fr_1.4fr_auto] sm:items-start"
                >
                  <div className="flex flex-col gap-1">
                    <label
                      htmlFor={`due-${String(row.key)}`}
                      className="text-xs text-muted-foreground"
                    >
                      {label} due
                    </label>
                    <Input
                      id={`due-${String(row.key)}`}
                      type="date"
                      value={row.dueOn}
                      aria-invalid={problem?.dueOn == null ? undefined : true}
                      onChange={(event) => {
                        update(row.key, { dueOn: event.target.value });
                      }}
                    />
                    {problem?.dueOn == null ? null : (
                      <span className="text-xs text-danger">{problem.dueOn}</span>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label
                      htmlFor={`amount-${String(row.key)}`}
                      className="text-xs text-muted-foreground"
                    >
                      Amount
                    </label>
                    <InputGroup>
                      <InputGroupAddon>₹</InputGroupAddon>
                      <InputGroupInput
                        id={`amount-${String(row.key)}`}
                        inputMode="decimal"
                        autoComplete="off"
                        className="tabular-nums"
                        value={row.amount}
                        aria-invalid={problem?.amount == null ? undefined : true}
                        onChange={(event) => {
                          update(row.key, { amount: event.target.value });
                        }}
                      />
                    </InputGroup>
                    {problem?.amount == null ? null : (
                      <span className="text-xs text-danger">{problem.amount}</span>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <label
                      htmlFor={`note-${String(row.key)}`}
                      className="text-xs text-muted-foreground"
                    >
                      Note (optional)
                    </label>
                    <Input
                      id={`note-${String(row.key)}`}
                      maxLength={80}
                      placeholder="Advance"
                      value={row.note}
                      onChange={(event) => {
                        update(row.key, { note: event.target.value });
                      }}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    className="sm:mt-5"
                    aria-label={`Remove ${label.toLowerCase()}`}
                    onClick={() => {
                      setRows((current) => current.filter((item) => item.key !== row.key));
                    }}
                  >
                    <Icon icon={Delete02Icon} />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={rows.length >= MAX_INSTALMENTS}
            onClick={() => {
              setRows((current) => [
                ...current,
                {
                  key: nextKey,
                  dueOn: todayInIndia(),
                  amount: fromPaise(Math.max(0, payable - total)),
                  note: "",
                },
              ]);
            }}
          >
            <Icon icon={Add01Icon} />
            Add an instalment
          </Button>
          <span
            className={cn(
              "text-sm tabular-nums",
              overProblem === null ? "text-muted-foreground" : "text-danger",
            )}
          >
            {formatInr(fromPaise(total), { paise: true })} of{" "}
            {formatInr(payments.payable, { paise: true })}
          </span>
        </div>
        {shown && overProblem !== null ? (
          <p role="alert" className="text-sm text-danger">
            {overProblem}
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
          Save instalments
        </Button>
      </DialogFooter>
    </form>
  );
}
