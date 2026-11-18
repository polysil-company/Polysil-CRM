"use client";

import { StarIcon } from "@hugeicons/core-free-icons";
import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import type * as React from "react";

import { ErrorState } from "@/components/patterns/error-state";
import { RelativeDate } from "@/components/patterns/relative-date";
import { StarRating } from "@/components/patterns/star-rating";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Icon } from "@/components/ui/icon";
import { Skeleton } from "@/components/ui/skeleton";
import type { Complaint } from "@/features/complaints/api/complaints.schemas";
import type { Order } from "@/features/orders/api/orders.schemas";
import { ratingListQueryOptions } from "@/features/ratings/api/ratings.queries";
import type { Rating, RatingListParams } from "@/features/ratings/api/ratings.schemas";
import {
  RATED_BY_LABELS,
  RATING_TARGET_LABELS,
  raterKindOf,
  SCORE_LABELS,
  starsText,
} from "@/features/ratings/lib/rating-labels";
import { useCan, useIsStaff } from "@/features/session/hooks/use-session";
import { isApiError } from "@/lib/api/errors";

import { RatingForm, type RatingSubject } from "./rating-form";

const TITLE_ID = "record-ratings-title";

type RatedRecord =
  | { readonly kind: "order"; readonly order: Order }
  | { readonly kind: "complaint"; readonly complaint: Complaint };

/** A shipped product on the order, once per product. */
interface ShippedProduct {
  readonly id: string;
  readonly name: string;
}

function shippedProductsOf(order: Order): ShippedProduct[] {
  const seen = new Map<string, ShippedProduct>();
  for (const line of order.lines) {
    if (Number(line.qtyDispatched) > 0 && !seen.has(line.productId)) {
      seen.set(line.productId, { id: line.productId, name: line.description });
    }
  }
  return [...seen.values()];
}

function paramsOf(record: RatedRecord): RatingListParams {
  return {
    target: null,
    salesOrderId: record.kind === "order" ? record.order.id : null,
    complaintId: record.kind === "complaint" ? record.complaint.id : null,
    partnerId: null,
    maxScore: null,
  };
}

/**
 * RATE-001, RATE-002 · The ratings on an order or a complaint, and the buttons to add one:
 * **Rate installation** once something has shipped, **Rate** on each shipped product, and
 * **Rate service** on a closed complaint. Each button goes once this kind of rater has rated it.
 * Hidden until there is something to rate or read, and on a 403.
 */
export function RecordRatingsCard(record: RatedRecord): React.JSX.Element | null {
  const staff = useIsStaff();
  const mayViewOrders = useCan("sales_orders", "view");
  const mayEditOrders = useCan("sales_orders", "edit");
  const mayViewComplaints = useCan("complaints", "view");
  const mayEditComplaints = useCan("complaints", "edit");
  const [subject, setSubject] = useState<RatingSubject | null>(null);

  const onOrder = record.kind === "order";
  const products = onOrder ? shippedProductsOf(record.order) : [];
  const rateable = onOrder ? products.length > 0 : record.complaint.status === "closed";
  const mayView = !staff || (onOrder ? mayViewOrders : mayViewComplaints);
  const mayRate = !staff || (onOrder ? mayEditOrders : mayEditComplaints);
  const query = useInfiniteQuery({
    ...ratingListQueryOptions(paramsOf(record)),
    enabled: mayView && rateable,
  });

  if (!mayView || !rateable) return null;
  if (query.status === "error" && isApiError(query.error) && query.error.status === 403) {
    return null;
  }

  const ratings = query.data?.pages.flatMap((page) => page.items) ?? [];
  const mine = raterKindOf(staff);
  const rated = (target: Rating["target"], productId?: string): boolean =>
    ratings.some(
      (rating) =>
        rating.target === target &&
        rating.ratedBy === mine &&
        (productId === undefined || rating.product?.id === productId),
    );
  const ready = query.status === "success" && mayRate;

  const installation: RatingSubject | null =
    onOrder && ready && !rated("installation")
      ? { target: "installation", salesOrderId: record.order.id, name: "the installation" }
      : null;
  const productSubjects: RatingSubject[] =
    onOrder && ready
      ? products
          .filter((product) => !rated("product", product.id))
          .map((product) => ({
            target: "product",
            salesOrderId: record.order.id,
            productId: product.id,
            name: product.name,
          }))
      : [];
  const service: RatingSubject | null =
    !onOrder && ready && !rated("service")
      ? { target: "service", complaintId: record.complaint.id, name: "the service" }
      : null;

  return (
    <section aria-labelledby={TITLE_ID}>
      <Card>
        <CardHeader className="flex-wrap">
          <div className="flex min-w-0 flex-col gap-0.5">
            <CardTitle level={3} id={TITLE_ID} className="flex items-center gap-2">
              <Icon icon={StarIcon} size="sm" className="text-muted-foreground" />
              Ratings
            </CardTitle>
            <CardDescription>
              {staff
                ? "What the farmer and the dealer said. A rating is never changed."
                : "Your firm's ratings, and the customer's score."}
            </CardDescription>
          </div>
          {installation === null && service === null ? null : (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSubject(installation ?? service);
              }}
            >
              {installation === null ? "Rate service" : "Rate installation"}
            </Button>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {query.status === "pending" ? (
            <div aria-busy="true" aria-label="Loading the ratings" className="flex flex-col gap-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : query.status === "error" ? (
            <ErrorState
              error={query.error}
              onRetry={() => {
                void query.refetch();
              }}
            />
          ) : ratings.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {mayRate ? "Not rated yet." : "Not rated yet. Those who handle it record ratings."}
            </p>
          ) : (
            <ul aria-label="Ratings" className="flex flex-col divide-y divide-border">
              {ratings.map((rating) => (
                <RatingRow key={rating.id} rating={rating} staff={staff} />
              ))}
            </ul>
          )}
          {productSubjects.length === 0 ? null : (
            <div className="flex flex-col gap-2">
              <h4 className="text-xs font-medium text-muted-foreground">Rate a product shipped</h4>
              <ul aria-label="Products to rate" className="flex flex-col gap-1.5">
                {productSubjects.map((product) => (
                  <li
                    key={product.productId}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="min-w-0 truncate text-foreground">{product.name}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Rate ${product.name}`}
                      onClick={() => {
                        setSubject(product);
                      }}
                    >
                      Rate
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={subject !== null}
        onOpenChange={(next) => {
          if (!next) setSubject(null);
        }}
      >
        <DialogContent size="sm">
          {subject === null ? null : (
            <RatingForm
              subject={subject}
              staff={staff}
              onDone={() => {
                setSubject(null);
              }}
            />
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}

/**
 * One rating: who, what, the stars with their word, the comment and who entered it. A dealer
 * reads a customer's rating as the score only.
 */
export function RatingRow({
  rating,
  staff,
  showDocument = false,
}: {
  rating: Rating;
  staff: boolean;
  /** On the ratings page, name the order or complaint it is on. */
  showDocument?: boolean;
}): React.JSX.Element {
  const scoreOnly = !staff && rating.ratedBy === "customer";
  const what =
    rating.target === "product" && rating.product !== null
      ? rating.product.name
      : RATING_TARGET_LABELS[rating.target];
  const document = rating.order ?? rating.complaint;
  return (
    <li className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="text-sm font-medium text-foreground">
          {scoreOnly ? "Customer rating" : `${RATED_BY_LABELS[rating.ratedBy]} · ${what}`}
        </span>
        <StarRating score={rating.score} />
        <span className="text-xs text-muted-foreground">
          {scoreOnly ? starsText(rating.score) : SCORE_LABELS[rating.score]}
        </span>
      </div>
      {rating.comment === null ? null : (
        <p className="text-sm text-foreground">&ldquo;{rating.comment}&rdquo;</p>
      )}
      <p className="text-xs text-muted-foreground">
        {showDocument && document !== null && document.number !== null ? (
          <>
            <Link
              href={
                rating.order === null
                  ? `/complaints/${document.id}`
                  : `/sales-orders/${document.id}`
              }
              className="font-mono text-primary-text underline-offset-4 hover:underline"
            >
              {document.number}
            </Link>
            {" · "}
          </>
        ) : null}
        {showDocument && rating.partner !== null ? `${rating.partner.name} · ` : ""}
        {rating.enteredBy === null
          ? rating.enteredVia === "portal"
            ? "By the farmer · "
            : ""
          : `Entered by ${rating.enteredBy.name} · `}
        <RelativeDate value={rating.createdAt} />
      </p>
    </li>
  );
}
