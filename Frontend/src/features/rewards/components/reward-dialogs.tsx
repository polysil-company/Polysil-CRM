"use client";

import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import type { RedemptionDecision } from "@/features/rewards/api/rewards.api";
import { useDecideRedemption } from "@/features/rewards/api/rewards.mutations";
import type { Redemption } from "@/features/rewards/api/rewards.schemas";
import { pointsText } from "@/features/rewards/lib/reward-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useCloseAfterSuccess } from "@/hooks/use-close-after-success";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { isApiError } from "@/lib/api/errors";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/rewards/components/reward-dialogs.tsx",
  dataId: "RWD-002",
});

const COPY: Readonly<
  Record<
    RedemptionDecision,
    {
      title: string;
      button: string;
      done: string;
      remark: "required" | "optional" | "none";
      note: string;
    }
  >
> = {
  fulfil: {
    title: "Mark the gift sent?",
    button: "Mark sent",
    done: "Gift marked sent",
    remark: "optional",
    note: "The points stay spent. Add how it went out, if that helps.",
  },
  reject: {
    title: "Refuse the gift?",
    button: "Refuse",
    done: "Gift refused",
    remark: "required",
    note: "The points go back to the balance, and the dealer sees your reason.",
  },
  withdraw: {
    title: "Withdraw the request?",
    button: "Withdraw",
    done: "Request withdrawn",
    remark: "none",
    note: "The points held for it go back to your balance.",
  },
};

/** RWD-001, RWD-002 · Send, refuse or withdraw a gift request, as the dialog's content. */
export function RedemptionDecisionForm({
  redemption,
  decision,
  onClose,
}: {
  redemption: Redemption;
  decision: RedemptionDecision;
  onClose: () => void;
}): React.JSX.Element {
  const decide = useDecideRedemption();
  const idempotency = useIdempotencyKey();
  const closeSoon = useCloseAfterSuccess(onClose);
  const copy = COPY[decision];
  const [remark, setRemark] = useState("");
  const [shown, setShown] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const problem = copy.remark === "required" && remark.trim() === "" ? "Say why." : null;
  const gift = redemption.gift?.name ?? "the gift";

  const submit = useAsyncAction({
    action: () => {
      const body = { remark: remark.trim() === "" ? null : remark.trim() };
      return decide.mutateAsync({
        redemptionId: redemption.id,
        decision,
        body,
        idempotencyKey: idempotency.keyFor({ id: redemption.id, decision, ...body }),
      });
    },
    logger: log,
    fn: `handle${decision[0]?.toUpperCase() ?? ""}${decision.slice(1)}Gift`,
    dataId: decision === "withdraw" ? "RWD-001" : "RWD-002",
    onSuccess: () => {
      idempotency.reset();
      toast.success(copy.done, { description: `${gift}, ${pointsText(redemption.points)}.` });
      closeSoon();
    },
    onError: (error) => {
      setRefusal(
        isApiError(error) && error.code === "redemption_closed"
          ? "It was already decided. Close and look again."
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
        <DialogTitle>{copy.title}</DialogTitle>
        <DialogDescription>
          {gift} for {redemption.holder.name ?? "the dealer"} · {pointsText(redemption.points)}
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">{copy.note}</p>
        {copy.remark === "none" ? null : (
          <Field data-invalid={shown && problem !== null ? true : undefined}>
            <FieldLabel htmlFor="redemption-remark">
              {copy.remark === "required" ? (
                "Why"
              ) : (
                <>
                  Note <span className="font-normal text-muted-foreground">(optional)</span>
                </>
              )}
            </FieldLabel>
            <Textarea
              id="redemption-remark"
              rows={2}
              maxLength={300}
              value={remark}
              aria-invalid={shown && problem !== null ? true : undefined}
              aria-describedby={shown && problem !== null ? "redemption-remark-error" : undefined}
              onChange={(event) => {
                setRemark(event.target.value);
              }}
            />
            {shown && problem !== null ? (
              <FieldError id="redemption-remark-error">{problem}</FieldError>
            ) : null}
          </Field>
        )}
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
          variant={decision === "fulfil" ? "primary" : "destructive"}
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
