"use client";

import { StarAward01Icon } from "@hugeicons/core-free-icons";
import { useQuery } from "@tanstack/react-query";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { StarRating } from "@/components/patterns/star-rating";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import { dealerRatingQueryOptions } from "@/features/ratings/api/ratings.queries";
import type { DealerRating } from "@/features/ratings/api/ratings.schemas";
import { averageText } from "@/features/ratings/lib/rating-labels";
import { isApiError } from "@/lib/api/errors";
import { formatInr, formatNumber } from "@/lib/format";

const TITLE_ID = "dealer-rating-title";

/** "the last year" for 365 days, else "the last 180 days". */
export function windowText(days: number): string {
  return days === 365 ? "the last year" : `the last ${formatNumber(days)} days`;
}

/**
 * RATE-004 · A dealer's rating, worked out by the backend on every read: the value-weighted days
 * from order to full payment and the order value over the window, each scored 1 to 5 by the
 * settings' bands, and their mean. Customers' feedback is shown apart. For staff who see
 * payments and for the dealer itself; a 403 hides it.
 */
export function DealerRatingCard({
  partnerId,
  title = "Dealer rating",
  level = 3,
}: {
  partnerId: string;
  title?: string;
  /** 2 where the card opens the page (My ledger), 3 under a page's own sections. */
  level?: 2 | 3;
}): React.JSX.Element | null {
  const query = useQuery(dealerRatingQueryOptions(partnerId));
  if (query.status === "error" && isApiError(query.error) && query.error.status === 403) {
    return null;
  }

  return (
    <section aria-labelledby={TITLE_ID}>
      <Card>
        <CardHeader className="flex-col gap-0.5">
          <CardTitle level={level} id={TITLE_ID} className="flex items-center gap-2">
            <Icon icon={StarAward01Icon} size="sm" className="text-muted-foreground" />
            {title}
          </CardTitle>
          {query.status === "success" ? (
            <CardDescription>
              From days to full payment and order value over {windowText(query.data.windowDays)}.
              Feedback is shown apart.
            </CardDescription>
          ) : null}
        </CardHeader>
        <CardContent>
          {query.status === "pending" ? (
            <div aria-busy="true" aria-label="Loading the rating" className="flex flex-col gap-3">
              <Skeleton className="h-10 w-32" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : query.status === "error" ? (
            <ErrorState
              error={query.error}
              onRetry={() => {
                void query.refetch();
              }}
            />
          ) : (
            <DealerRatingBody rating={query.data} />
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function DealerRatingBody({ rating }: { rating: DealerRating }): React.JSX.Element {
  return (
    <div className="flex flex-col gap-4">
      {rating.rating === null ? (
        <div className="flex flex-col gap-0.5">
          <p className="text-lg font-semibold text-foreground">Not rated yet</p>
          <p className="text-sm text-muted-foreground">
            {rating.orders === 0
              ? `No order counts in ${windowText(rating.windowDays)}.`
              : "No order is paid in full yet, so there are no days to payment to score."}
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-3xl font-semibold text-foreground tabular-nums">
            {averageText(rating.rating)}
            <span className="text-base font-normal text-muted-foreground"> / 5</span>
          </p>
          <StarRating score={rating.rating} size="md" />
        </div>
      )}
      <dl className="grid gap-3 sm:grid-cols-2">
        <Figure
          label="Days to full payment"
          value={rating.paymentDays === null ? "—" : `${formatNumber(rating.paymentDays, 1)} days`}
          score={rating.paymentScore}
          note={`${formatNumber(rating.paidOrders)} of ${formatNumber(rating.orders)} orders paid in full`}
        />
        <Figure
          label="Order value, before GST"
          value={formatInr(rating.orderValue)}
          score={rating.valueScore}
          note={`${formatNumber(rating.orders)} ${rating.orders === 1 ? "order" : "orders"} counted`}
        />
      </dl>
      <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3 text-sm">
        <span className="text-muted-foreground">Customers&apos; feedback</span>
        {rating.feedback.average === null ? (
          <span className="text-foreground">none yet</span>
        ) : (
          <>
            <StarRating score={rating.feedback.average} size="xs" />
            <span className="text-foreground tabular-nums">
              {averageText(rating.feedback.average)} from {formatNumber(rating.feedback.count)}{" "}
              {rating.feedback.count === 1 ? "rating" : "ratings"}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

function Figure({
  label,
  value,
  score,
  note,
}: {
  label: string;
  value: string;
  score: number | null;
  note: string;
}): React.JSX.Element {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground tabular-nums">{value}</span>
        {score === null ? null : (
          <Badge variant={score >= 4 ? "success" : score >= 3 ? "neutral" : "warning"} size="sm">
            {score} of 5
          </Badge>
        )}
      </dd>
      <dd className="text-xs text-muted-foreground">{note}</dd>
    </div>
  );
}
