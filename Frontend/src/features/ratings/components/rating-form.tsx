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
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Textarea } from "@/components/ui/textarea";
import { useCreateRating } from "@/features/ratings/api/ratings.mutations";
import {
  RATING_COMMENT_MAX,
  type RatingCreateRequest,
  type RatingTarget,
} from "@/features/ratings/api/ratings.schemas";
import { ratingRefusal, SCORE_LABELS } from "@/features/ratings/lib/rating-labels";
import { useAsyncAction } from "@/hooks/use-async-action";
import { useIdempotencyKey } from "@/hooks/use-idempotency-key";
import { toUserFacingError } from "@/lib/api/error-messages";
import { formatNumber } from "@/lib/format";
import { createLogger } from "@/lib/logger";

const log = createLogger({
  file: "features/ratings/components/rating-form.tsx",
  dataId: "RATE-001",
});

/** What is being rated, and how the form names it. */
export interface RatingSubject {
  readonly target: RatingTarget;
  readonly salesOrderId?: string;
  readonly complaintId?: string;
  readonly productId?: string;
  /** "the installation", "Drip lateral 16 mm", "the service on CMP/…". */
  readonly name: string;
}

const QUESTIONS: Readonly<Record<RatingTarget, string>> = {
  installation: "How was the installation?",
  product: "How is the product?",
  service: "How was the service?",
};

/** The request for a subject, a score and the comment as typed. */
export function ratingRequestOf(
  subject: RatingSubject,
  score: number,
  comment: string,
): RatingCreateRequest {
  return {
    target: subject.target,
    sales_order_id: subject.salesOrderId ?? null,
    complaint_id: subject.complaintId ?? null,
    product_id: subject.productId ?? null,
    score,
    comment: comment.trim() === "" ? null : comment.trim(),
  };
}

/**
 * RATE-001 · Record one rating: 1 to 5 stars and an optional comment. Staff record what the
 * farmer said; a dealer's user rates for its firm. A rating is never changed, so the form says so.
 */
export function RatingForm({
  subject,
  staff,
  onDone,
}: {
  subject: RatingSubject;
  staff: boolean;
  onDone: () => void;
}): React.JSX.Element {
  const [score, setScore] = useState<number | null>(null);
  const [comment, setComment] = useState("");
  const [missing, setMissing] = useState(false);
  const [refusal, setRefusal] = useState<string | null>(null);
  const mutation = useCreateRating();
  const idempotency = useIdempotencyKey();

  const save = useAsyncAction({
    action: () => {
      const body = ratingRequestOf(subject, score ?? 0, comment);
      return mutation.mutateAsync({ body, idempotencyKey: idempotency.keyFor(body) });
    },
    logger: log,
    fn: "handleCreateRating",
    dataId: "RATE-001",
    onSuccess: () => {
      idempotency.reset();
      toast.success("Rating saved", { description: subject.name });
      onDone();
    },
    onError: (error) => {
      const words = ratingRefusal(error);
      if (words !== null) {
        setRefusal(words);
        return;
      }
      toast.error("Rating not saved", { description: toUserFacingError(error).description });
    },
  });

  return (
    <form
      noValidate
      aria-label={`Rate ${subject.name}`}
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => {
        event.preventDefault();
        setMissing(score === null);
        if (score !== null) void save.run();
      }}
    >
      <DialogHeader>
        <DialogTitle>Rate {subject.name}</DialogTitle>
        <DialogDescription>
          {staff
            ? "What the farmer said, in their words. A rating is kept as it is: it can't be changed later."
            : "Your firm's rating of Polysil. It can't be changed later."}
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
            legend={QUESTIONS[subject.target]}
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
          <FieldLabel htmlFor="rating-comment">
            Comment <span className="font-normal text-muted-foreground">(optional)</span>
          </FieldLabel>
          <Textarea
            id="rating-comment"
            rows={3}
            value={comment}
            maxLength={RATING_COMMENT_MAX}
            placeholder={staff ? "What went well, or what didn't" : "Anything Polysil should know"}
            aria-describedby="rating-comment-count"
            onChange={(event) => {
              setComment(event.target.value);
            }}
          />
          <FieldDescription id="rating-comment-count" className="tabular-nums">
            {formatNumber(comment.length)} of {formatNumber(RATING_COMMENT_MAX)} characters
          </FieldDescription>
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
          Save rating
        </Button>
      </DialogFooter>
    </form>
  );
}
