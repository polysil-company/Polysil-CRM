"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useActOnMarketingOrder,
  useDispatchMarketingOrder,
} from "@/features/marketing/api/marketing.mutations";
import { marketingOrderQueryOptions } from "@/features/marketing/api/marketing.queries";
import type { MarketingAction, MarketingOrder } from "@/features/marketing/api/marketing.schemas";
import {
  MARKETING_STATUS_BADGE,
  MARKETING_STATUS_LABELS,
  percentText,
} from "@/features/marketing/lib/marketing-labels";
import { formatBusinessDay } from "@/features/subsidy/lib/application-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { formatInr, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/marketing/components/marketing-order-dialog.tsx",
  dataId: "MKT-004",
});

type Step = "view" | MarketingAction | "dispatch";

/**
 * MKT-003, MKT-004 · One marketing order: its lines with both shares, who asked, the decision
 * and the dispatch. The buttons come from the order's `can`: approve or refuse (the District
 * Manager, never on their own order), cancel, and record the dispatch (the marketing team).
 */
export function MarketingOrderDialog({
  orderId,
  onClose,
}: {
  orderId: string;
  onClose: () => void;
}): React.JSX.Element {
  const query = useQuery(marketingOrderQueryOptions(orderId));
  const [step, setStep] = useState<Step>("view");

  if (query.status === "pending") {
    return (
      <>
        <DialogHeader>
          <DialogTitle>Marketing order</DialogTitle>
          <DialogDescription>Loading…</DialogDescription>
        </DialogHeader>
        <DialogBody aria-busy="true" className="flex flex-col gap-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-24 w-full" />
        </DialogBody>
      </>
    );
  }
  if (query.status === "error") {
    return (
      <>
        <DialogHeader>
          <DialogTitle>Marketing order</DialogTitle>
          <DialogDescription>It couldn&apos;t be opened.</DialogDescription>
        </DialogHeader>
        <DialogBody>
          <ErrorState
            error={query.error}
            onRetry={() => {
              void query.refetch();
            }}
          />
        </DialogBody>
      </>
    );
  }
  const order = query.data;
  if (step === "dispatch") {
    return (
      <DispatchForm
        order={order}
        onBack={() => {
          setStep("view");
        }}
        onDone={onClose}
      />
    );
  }
  if (step !== "view") {
    return (
      <RemarkForm
        order={order}
        action={step}
        onBack={() => {
          setStep("view");
        }}
        onDone={onClose}
      />
    );
  }
  return <OrderView order={order} onStep={setStep} />;
}

function OrderView({
  order,
  onStep,
}: {
  order: MarketingOrder;
  onStep: (step: Step) => void;
}): React.JSX.Element {
  const money = (value: string): string => formatInr(value, { paise: true });
  const anyAction = order.can.approve || order.can.reject || order.can.cancel || order.can.dispatch;
  return (
    <>
      <DialogHeader>
        <DialogTitle className="flex flex-wrap items-center gap-2">
          <span className="font-mono">{order.orderNo}</span>
          <Badge variant={MARKETING_STATUS_BADGE[order.status]} dot>
            {MARKETING_STATUS_LABELS[order.status]}
          </Badge>
        </DialogTitle>
        <DialogDescription>
          {order.partner === null
            ? "For the office's own use"
            : `For ${order.partner.name ?? "a dealer"}`}{" "}
          · {order.office.name ?? "an office"} · asked by {order.requestedBy.name ?? "someone"}{" "}
          <RelativeDate value={order.createdAt} />
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-lg text-sm">
            <caption className="sr-only">Items, with what the company and the dealer pay</caption>
            <thead className="bg-muted text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  Item
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Qty
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Value
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Company
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Dealer
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {order.lines.map((line) => (
                <tr key={line.id}>
                  <td className="px-3 py-2">
                    <span className="block text-foreground">{line.material.name}</span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {money(line.price)} / {line.unit} · company{" "}
                      {percentText(line.companySharePct)}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{line.qty}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(line.value)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(line.companyShare)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(line.dealerShare)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t border-border font-semibold">
              <tr>
                <th scope="row" colSpan={2} className="px-3 py-2 text-left">
                  Total
                </th>
                <td className="px-3 py-2 text-right tabular-nums">{money(order.totals.value)}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {money(order.totals.companyShare)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {money(order.totals.dealerShare)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        {order.provisional ? (
          <p className="text-xs text-muted-foreground">
            Some prices on it were indicative when it was placed.
          </p>
        ) : null}
        {order.remark === null ? null : (
          <p className="text-sm text-foreground">
            <span className="text-muted-foreground">Remark: </span>
            {order.remark}
          </p>
        )}
        {order.decision === null ? null : (
          <p className="rounded-lg bg-muted p-3 text-sm text-foreground">
            {order.decision.status === "approved" ? "Approved" : "Refused"}
            {order.decision.by === null ? "" : ` by ${order.decision.by.name ?? "someone"}`}{" "}
            <RelativeDate value={order.decision.at} />
            {order.decision.remark === null ? "" : `: ${order.decision.remark}`}
          </p>
        )}
        {order.dispatch === null ? null : (
          <p className="rounded-lg bg-success-soft p-3 text-sm text-foreground">
            Sent on {formatBusinessDay(order.dispatch.dispatchedOn)} · {order.dispatch.reference}
            {order.dispatch.by === null ? "" : ` · by ${order.dispatch.by.name ?? "someone"}`}
          </p>
        )}
        {order.cancelRemark === null ? null : (
          <p className="rounded-lg bg-muted p-3 text-sm text-foreground">
            Cancelled: {order.cancelRemark}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant={anyAction ? "ghost" : "outline"} />}>
          Close
        </DialogClose>
        {order.can.cancel ? (
          <Button
            variant="outline"
            onClick={() => {
              onStep("cancel");
            }}
          >
            Cancel order
          </Button>
        ) : null}
        {order.can.reject ? (
          <Button
            variant="outline"
            onClick={() => {
              onStep("reject");
            }}
          >
            Refuse
          </Button>
        ) : null}
        {order.can.approve ? (
          <Button
            onClick={() => {
              onStep("approve");
            }}
          >
            Approve
          </Button>
        ) : null}
        {order.can.dispatch ? (
          <Button
            onClick={() => {
              onStep("dispatch");
            }}
          >
            Record dispatch
          </Button>
        ) : null}
      </DialogFooter>
    </>
  );
}

const ACTION_COPY: Readonly<
  Record<MarketingAction, { title: string; verb: string; done: string; busy: string }>
> = {
  approve: {
    title: "Approve this order?",
    verb: "Approve",
    done: "Order approved",
    busy: "Approving…",
  },
  reject: { title: "Refuse this order?", verb: "Refuse", done: "Order refused", busy: "Refusing…" },
  cancel: {
    title: "Cancel this order?",
    verb: "Cancel order",
    done: "Order cancelled",
    busy: "Cancelling…",
  },
};

/** A refusal's words for what the backend said. */
function refusalText(error: unknown): string {
  if (isApiError(error)) {
    if (error.code === "status_changed") return "Someone acted on it first. Close and look again.";
    if (error.code === "own_order") return "Nobody approves their own order.";
    if (error.code === "not_your_approval") return "This order isn't yours to decide.";
  }
  return toUserFacingError(error).title;
}

function RemarkForm({
  order,
  action,
  onBack,
  onDone,
}: {
  order: MarketingOrder;
  action: MarketingAction;
  onBack: () => void;
  onDone: () => void;
}): React.JSX.Element {
  const act = useActOnMarketingOrder();
  const idempotency = useIdempotencyKey();
  const [remark, setRemark] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const copy = ACTION_COPY[action];
  const required = action === "reject" || (action === "cancel" && order.status === "approved");
  const problem = required && remark.trim() === "" ? "Say why." : null;

  const submit = useAsyncAction({
    action: () => {
      const body = { remark: remark.trim() === "" ? null : remark.trim() };
      return act.mutateAsync({
        orderId: order.id,
        action,
        body,
        idempotencyKey: idempotency.keyFor({ id: order.id, action, ...body }),
      });
    },
    logger: log,
    fn: "handleMarketingOrderAction",
    dataId: "MKT-004",
    onSuccess: () => {
      idempotency.reset();
      toast.success(copy.done, { description: order.orderNo });
      onDone();
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.code === "remark_required" ? "Say why." : refusalText(error),
      );
    },
  });

  return (
    <form
      noValidate
      aria-label={copy.title}
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
        <DialogTitle>{copy.title}</DialogTitle>
        <DialogDescription>
          <span className="font-mono">{order.orderNo}</span> ·{" "}
          {formatInr(order.totals.value, { paise: true })}
          {order.partner === null ? " · office use" : ` · ${order.partner.name ?? "a dealer"}`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3">
        <Field data-invalid={shown && problem !== null ? true : undefined}>
          <FieldLabel htmlFor="marketing-action-remark">
            {required ? "Why" : "Remark (optional)"}
          </FieldLabel>
          <Textarea
            id="marketing-action-remark"
            rows={2}
            maxLength={500}
            value={remark}
            aria-invalid={shown && problem !== null ? true : undefined}
            aria-describedby={
              shown && problem !== null ? "marketing-action-remark-error" : undefined
            }
            onChange={(event) => {
              setRemark(event.target.value);
            }}
          />
          {shown && problem !== null ? (
            <FieldError id="marketing-action-remark-error">{problem}</FieldError>
          ) : null}
        </Field>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <Button type="button" variant="outline" disabled={submit.isBusy} onClick={onBack}>
          Back
        </Button>
        <Button
          type="submit"
          variant={action === "approve" ? "primary" : "destructive"}
          state={submit.state}
          loadingLabel={copy.busy}
          successLabel="Done"
          errorLabel="Not done"
        >
          {copy.verb}
        </Button>
      </DialogFooter>
    </form>
  );
}

function DispatchForm({
  order,
  onBack,
  onDone,
}: {
  order: MarketingOrder;
  onBack: () => void;
  onDone: () => void;
}): React.JSX.Element {
  const dispatch = useDispatchMarketingOrder();
  const idempotency = useIdempotencyKey();
  const today = todayInIndia();
  const [on, setOn] = useState(today);
  const [reference, setReference] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const problems = {
    on: on === "" ? "Pick the date it was sent." : on > today ? "Not in the future." : null,
    reference: reference.trim() === "" ? "Say how it was sent, like a docket number." : null,
  };
  const invalid = problems.on !== null || problems.reference !== null;

  const submit = useAsyncAction({
    action: () => {
      const body = { dispatched_on: on, reference: reference.trim() };
      return dispatch.mutateAsync({
        orderId: order.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: order.id, ...body }),
      });
    },
    logger: log,
    fn: "handleDispatchMarketingOrder",
    dataId: "MKT-004",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Dispatch recorded", { description: order.orderNo });
      onDone();
    },
    onError: (error) => {
      setRefusal(refusalText(error));
    },
  });

  return (
    <form
      noValidate
      aria-label="Record the dispatch"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (invalid) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Record the dispatch</DialogTitle>
        <DialogDescription>
          <span className="font-mono">{order.orderNo}</span>
          {order.partner === null ? " · office use" : ` · to ${order.partner.name ?? "a dealer"}`}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-3 sm:flex-row">
        <Field className="sm:w-44" data-invalid={shown && problems.on !== null ? true : undefined}>
          <FieldLabel htmlFor="marketing-dispatched-on">Sent on</FieldLabel>
          <Input
            id="marketing-dispatched-on"
            type="date"
            max={today}
            value={on}
            aria-invalid={shown && problems.on !== null ? true : undefined}
            aria-describedby={
              shown && problems.on !== null ? "marketing-dispatched-on-error" : undefined
            }
            onChange={(event) => {
              setOn(event.target.value);
            }}
          />
          {shown && problems.on !== null ? (
            <FieldError id="marketing-dispatched-on-error">{problems.on}</FieldError>
          ) : null}
        </Field>
        <Field
          className="flex-1"
          data-invalid={shown && problems.reference !== null ? true : undefined}
        >
          <FieldLabel htmlFor="marketing-reference">Reference</FieldLabel>
          <Input
            id="marketing-reference"
            placeholder="DTDC 4471 2208"
            maxLength={120}
            value={reference}
            aria-invalid={shown && problems.reference !== null ? true : undefined}
            aria-describedby={
              shown && problems.reference !== null ? "marketing-reference-error" : undefined
            }
            onChange={(event) => {
              setReference(event.target.value);
            }}
          />
          {shown && problems.reference !== null ? (
            <FieldError id="marketing-reference-error">{problems.reference}</FieldError>
          ) : null}
        </Field>
      </DialogBody>
      {refusal === null ? null : (
        <p role="alert" className="mx-5 rounded-md bg-danger-soft p-3 text-sm text-danger">
          {refusal}
        </p>
      )}
      <DialogFooter>
        <Button type="button" variant="outline" disabled={submit.isBusy} onClick={onBack}>
          Back
        </Button>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Saved"
          errorLabel="Not saved"
        >
          Record dispatch
        </Button>
      </DialogFooter>
    </form>
  );
}
