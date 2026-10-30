"use client";

import { useState } from "react";
import type * as React from "react";
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
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { CommissionDecision } from "@/features/commission/api/commission.api";
import {
  useDecideCommission,
  usePayCommission,
} from "@/features/commission/api/commission.mutations";
import type { Commission } from "@/features/commission/api/commission.schemas";
import { useCan, useSession } from "@/features/session/hooks/use-session";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError, readFieldErrors } from "@/lib/api/errors";
import { formatInr, todayInIndia } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/commission/components/commission-decisions.tsx",
  dataId: "SUBS-017",
});

type Opened = CommissionDecision | "pay";

/** What each role may do to a commission now, as the backend's router allows it. */
export function useCommissionActions(commission: Commission): {
  readonly approve: boolean;
  readonly returnIt: boolean;
  readonly cancel: boolean;
  readonly pay: boolean;
  /** Approving is not for whoever recorded it (403 own_decision). */
  readonly recordedByMe: boolean;
} {
  const session = useSession();
  const accounts = useCan("payments", "approve");
  const pays = useCan("payments", "edit");
  const coordinator = useCan("subsidy", "view");
  const waiting = commission.status === "calculated";
  const recordedByMe = session.data?.user.id === commission.recordedBy.id;
  return {
    approve: accounts && waiting && !recordedByMe,
    returnIt: accounts && waiting,
    cancel:
      (coordinator && (waiting || commission.status === "returned")) ||
      (accounts && commission.status === "approved"),
    pay: pays && commission.status === "approved",
    recordedByMe: accounts && waiting && recordedByMe,
  };
}

/**
 * SUBS-017 · Approve, return, cancel and pay a commission, each with the role that may. A
 * return or cancel needs a remark; a payment its date and reference.
 */
export function CommissionActions({
  commission,
  size = "md",
}: {
  commission: Commission;
  size?: "md" | "sm";
}): React.JSX.Element | null {
  const actions = useCommissionActions(commission);
  const [opened, setOpened] = useState<Opened | null>(null);
  const any = actions.approve || actions.returnIt || actions.cancel || actions.pay;
  if (!any && !actions.recordedByMe) return null;
  const name = `${commission.application.number}, ${commission.partner.name ?? "the dealer"}`;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {actions.approve ? (
        <Button
          size={size}
          aria-label={`Approve the commission on ${name}`}
          onClick={() => {
            setOpened("approve");
          }}
        >
          Approve
        </Button>
      ) : null}
      {actions.pay ? (
        <Button
          size={size}
          aria-label={`Record the payment on ${name}`}
          onClick={() => {
            setOpened("pay");
          }}
        >
          Record payment
        </Button>
      ) : null}
      {actions.returnIt ? (
        <Button
          size={size}
          variant="outline"
          aria-label={`Return the commission on ${name}`}
          onClick={() => {
            setOpened("return");
          }}
        >
          Return
        </Button>
      ) : null}
      {actions.cancel ? (
        <Button
          size={size}
          variant="ghost"
          aria-label={`Cancel the commission on ${name}`}
          onClick={() => {
            setOpened("cancel");
          }}
        >
          Cancel it
        </Button>
      ) : null}
      {actions.recordedByMe ? (
        <p className="text-xs text-muted-foreground">
          You recorded it, so someone else approves it.
        </p>
      ) : null}

      <Dialog
        open={opened !== null}
        onOpenChange={(open) => {
          if (!open) setOpened(null);
        }}
      >
        <DialogContent size="sm">
          {opened === null ? null : opened === "pay" ? (
            <PayForm
              commission={commission}
              onClose={() => {
                setOpened(null);
              }}
            />
          ) : (
            <DecisionForm
              commission={commission}
              decision={opened}
              onClose={() => {
                setOpened(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

const DECISION_COPY: Readonly<
  Record<
    CommissionDecision,
    { title: string; button: string; done: string; needsRemark: boolean; note: string }
  >
> = {
  approve: {
    title: "Approve the commission?",
    button: "Approve",
    done: "Commission approved",
    needsRemark: false,
    note: "It moves to To pay. Its figures can't be recorded again once approved.",
  },
  return: {
    title: "Return the commission?",
    button: "Return",
    done: "Commission returned",
    needsRemark: true,
    note: "The co-ordinator sees your remark and records it again.",
  },
  cancel: {
    title: "Cancel the commission?",
    button: "Cancel the commission",
    done: "Commission cancelled",
    needsRemark: true,
    note: "A new one can then be recorded on the application.",
  },
};

/** A refusal in words: someone moved it, or the rule it broke. */
function refusalText(error: unknown): string {
  if (isApiError(error)) {
    if (error.code === "status_changed")
      return "It has moved on since you opened it. Close and look again.";
    if (error.code === "own_decision") return "You recorded it, so someone else approves it.";
    if (error.code === "remark_required") return "Say why.";
  }
  return toUserFacingError(error).title;
}

function DecisionForm({
  commission,
  decision,
  onClose,
}: {
  commission: Commission;
  decision: CommissionDecision;
  onClose: () => void;
}): React.JSX.Element {
  const decide = useDecideCommission();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const copy = DECISION_COPY[decision];
  const [remark, setRemark] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const remarkProblem = copy.needsRemark && remark.trim() === "" ? "Say why." : null;

  const submit = useAsyncAction({
    action: () => {
      const body = { remark: remark.trim() === "" ? null : remark.trim() };
      return decide.mutateAsync({
        commissionId: commission.id,
        decision,
        body,
        idempotencyKey: idempotency.keyFor({ id: commission.id, decision, ...body }),
      });
    },
    logger: log,
    fn: `handle${decision[0]?.toUpperCase() ?? ""}${decision.slice(1)}Commission`,
    dataId: "SUBS-017",
    onSuccess: () => {
      idempotency.reset();
      toast.success(copy.done, { description: commission.application.number });
      closeSoon();
    },
    onError: (error) => {
      setRefusal(refusalText(error));
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
        if (remarkProblem !== null) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>{copy.title}</DialogTitle>
        <DialogDescription>
          {commission.application.number} · {commission.partner.name ?? "The dealer"} ·{" "}
          {formatInr(commission.total, { paise: true })}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">{copy.note}</p>
        {copy.needsRemark ? (
          <Field data-invalid={shown && remarkProblem !== null ? true : undefined}>
            <FieldLabel htmlFor="commission-remark">Why</FieldLabel>
            <Textarea
              id="commission-remark"
              rows={3}
              maxLength={500}
              value={remark}
              aria-invalid={shown && remarkProblem !== null ? true : undefined}
              aria-describedby={
                shown && remarkProblem !== null ? "commission-remark-error" : undefined
              }
              onChange={(event) => {
                setRemark(event.target.value);
              }}
            />
            {shown && remarkProblem !== null ? (
              <FieldError id="commission-remark-error">{remarkProblem}</FieldError>
            ) : null}
          </Field>
        ) : null}
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Not now
        </DialogClose>
        <Button
          type="submit"
          variant={decision === "approve" ? "primary" : "destructive"}
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Done"
          errorLabel="Not done"
        >
          {copy.button}
        </Button>
      </DialogFooter>
    </form>
  );
}

function PayForm({
  commission,
  onClose,
}: {
  commission: Commission;
  onClose: () => void;
}): React.JSX.Element {
  const pay = usePayCommission();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const today = todayInIndia();
  const [paidOn, setPaidOn] = useState(today);
  const [reference, setReference] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Readonly<Record<string, string>>>({});
  const problems = {
    paid_on:
      fieldErrors.paid_on ??
      (!/^\d{4}-\d{2}-\d{2}$/.test(paidOn)
        ? "Choose the day it was paid."
        : paidOn > today
          ? "Not in the future."
          : null),
    payment_reference:
      fieldErrors.payment_reference ??
      (reference.trim() === "" ? "Give the UTR or cheque number." : null),
  };

  const submit = useAsyncAction({
    action: () => {
      const body = { paid_on: paidOn, payment_reference: reference.trim() };
      return pay.mutateAsync({
        commissionId: commission.id,
        body,
        idempotencyKey: idempotency.keyFor({ id: commission.id, ...body }),
      });
    },
    logger: log,
    fn: "handlePayCommission",
    dataId: "SUBS-017",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Payment recorded", {
        description: `${commission.application.number} · ${formatInr(commission.total, { paise: true })}`,
      });
      closeSoon();
    },
    onError: (error) => {
      const fields = readFieldErrors(error);
      if (fields !== null) setFieldErrors(fields);
      else setRefusal(refusalText(error));
    },
  });
  const show = (key: keyof typeof problems): string | null => (shown ? problems[key] : null);

  return (
    <form
      noValidate
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setShown(true);
        setRefusal(null);
        if (Object.values(problems).some((problem) => problem !== null)) return;
        void submit.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Record the payment</DialogTitle>
        <DialogDescription>
          {formatInr(commission.total, { paise: true })} to{" "}
          {commission.partner.name ?? "the dealer"} for {commission.application.number}.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <Field data-invalid={show("paid_on") === null ? undefined : true}>
          <FieldLabel htmlFor="commission-paid-on">Paid on</FieldLabel>
          <Input
            id="commission-paid-on"
            type="date"
            max={today}
            value={paidOn}
            aria-invalid={show("paid_on") === null ? undefined : true}
            aria-describedby={show("paid_on") === null ? undefined : "commission-paid-on-error"}
            onChange={(event) => {
              setPaidOn(event.target.value);
              setFieldErrors(({ paid_on: _paidOn, ...rest }) => rest);
            }}
          />
          {show("paid_on") === null ? null : (
            <FieldError id="commission-paid-on-error">{show("paid_on")}</FieldError>
          )}
        </Field>
        <Field data-invalid={show("payment_reference") === null ? undefined : true}>
          <FieldLabel htmlFor="commission-reference">Payment reference</FieldLabel>
          <Input
            id="commission-reference"
            autoComplete="off"
            maxLength={120}
            placeholder="NEFT UTR, or the cheque number"
            value={reference}
            aria-invalid={show("payment_reference") === null ? undefined : true}
            aria-describedby={
              show("payment_reference") === null
                ? "commission-reference-hint"
                : "commission-reference-error"
            }
            onChange={(event) => {
              setReference(event.target.value);
              setFieldErrors(({ payment_reference: _reference, ...rest }) => rest);
            }}
          />
          {show("payment_reference") === null ? (
            <FieldDescription id="commission-reference-hint">
              So the dealer&apos;s statement can be matched.
            </FieldDescription>
          ) : (
            <FieldError id="commission-reference-error">{show("payment_reference")}</FieldError>
          )}
        </Field>
        {refusal === null ? null : (
          <p role="alert" className="rounded-md bg-danger-soft p-3 text-sm text-danger">
            {refusal}
          </p>
        )}
      </DialogBody>
      <DialogFooter>
        <DialogClose render={<Button type="button" variant="outline" disabled={submit.isBusy} />}>
          Not now
        </DialogClose>
        <Button
          type="submit"
          state={submit.state}
          loadingLabel="Saving…"
          successLabel="Recorded"
          errorLabel="Not recorded"
        >
          Record payment
        </Button>
      </DialogFooter>
    </form>
  );
}
