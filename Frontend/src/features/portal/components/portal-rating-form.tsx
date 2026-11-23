"use client";

import { useState } from "react";
import type * as React from "react";
import { toast } from "sonner";

import { Notice } from "@/components/patterns/notice";
import { StarRatingInput } from "@/components/patterns/star-rating";
import { Button } from "@/components/ui/button";
import {
  DialogBody,
  DialogClose,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { useCreatePortalRating } from "@/features/portal/api/portal.mutations";
import type { PortalRatingRequest } from "@/features/portal/api/portal.schemas";
import { portalRatingRefusal } from "@/features/portal/lib/portal-labels";
import { SCORE_LABELS } from "@/features/ratings/lib/rating-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/portal/components/portal-rating-form.tsx",
  dataId: "FARM-003",
});

/** What the farmer is rating: an order's installation or a complaint's service, by number. */
export type PortalRatingSubject =
  | { readonly target: "installation"; readonly orderNo: string }
  | { readonly target: "service"; readonly complaintNo: string };

function requestOf(
  subject: PortalRatingSubject,
  score: number,
  comment: string,
): PortalRatingRequest {
  return {
    target: subject.target,
    order_no: subject.target === "installation" ? subject.orderNo : null,
    complaint_no: subject.target === "service" ? subject.complaintNo : null,
    score,
    comment: comment.trim() === "" ? null : comment.trim(),
  };
}

/**
 * FARM-003 · The farmer rates the installation of an order or the service on a complaint:
 * 1 to 5 stars and, if he likes, a few words. A refusal that means the button should go
 * (`not_rateable`, `rating_exists`) is passed up so the page can hide it.
 */
export function PortalRatingForm({
  subject,
  onDone,
  onRefused,
}: {
  subject: PortalRatingSubject;
  onDone: () => void;
  onRefused: () => void;
}): React.JSX.Element {
  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [missing, setMissing] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const mutation = useCreatePortalRating();
  const idempotency = useIdempotencyKey();
  const what =
    subject.target === "installation"
      ? `the installation of ${subject.orderNo}`
      : `the service on ${subject.complaintNo}`;

  const save = useAsyncAction({
    action: () => {
      const body = requestOf(subject, score ?? 0, comment);
      return mutation.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handlePortalRating",
    dataId: "FARM-003",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Thank you for your rating");
      onDone();
    },
    onError: (error) => {
      const words = portalRatingRefusal(error);
      if (words !== null) {
        setRefusal(words);
        onRefused();
        return;
      }
      toast.error("Your rating wasn't saved", {
        description: toUserFacingError(error).description,
      });
    },
  });

  return (
    <form
      noValidate
      aria-label={`Rate ${what}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setMissing(score === null);
        if (score !== null) void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>
          {subject.target === "installation" ? "Rate the installation" : "Rate the service"}
        </DialogTitle>
        <DialogDescription>
          {subject.target === "installation"
            ? `How was the installation of ${subject.orderNo}?`
            : `How did we handle complaint ${subject.complaintNo}?`}{" "}
          Your rating can&apos;t be changed later.
        </DialogDescription>
      </DialogHeader>
      <DialogBody className="flex flex-col gap-4">
        {refusal === null ? null : (
          <Notice tone="warning">
            <span role="alert">{refusal}</span>
          </Notice>
        )}
        <div>
          <StarRatingInput
            legend="Your stars"
            value={score}
            onValueChange={(next) => {
              setScore(next);
              setMissing(false);
            }}
            describe={(value) => SCORE_LABELS[value] ?? ""}
            invalid={missing}
            disabled={save.isBusy}
          />
          {missing ? (
            <p role="alert" className="text-sm text-danger">
              Choose how many stars.
            </p>
          ) : null}
        </div>
        <Field>
          <FieldLabel htmlFor="portal-rating-comment">
            Anything to add? <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="portal-rating-comment"
            rows={3}
            value={comment}
            maxLength={1000}
            onChange={(event) => {
              setComment(event.target.value);
            }}
          />
        </Field>
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
          Send rating
        </Button>
      </DialogFooter>
    </form>
  );
}
