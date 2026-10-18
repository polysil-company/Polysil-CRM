import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  dealerRatingSchema,
  RATING_PAGE_SIZE,
  ratingEnvelopeSchema,
  ratingPageSchema,
  ratingSummarySchema,
  type DealerRating,
  type Rating,
  type RatingCreateRequest,
  type RatingListParams,
  type RatingPage,
  type RatingSummaryGroup,
  type RatingSummaryRow,
} from "./ratings.schemas";

const log = createLogger({ file: "features/ratings/api/ratings.api.ts", dataId: "RATE-002" });

/** RATE-001 · Record one rating. 409 `rating_exists`; 422 `not_rateable`, `product_not_shipped`. */
export function createRating({
  body,
  idempotencyKey,
}: {
  readonly body: RatingCreateRequest;
  readonly idempotencyKey: string;
}): Promise<Rating> {
  return apiRequest({
    dataId: "RATE-001",
    logger: log,
    fn: "createRating",
    method: "POST",
    path: "/ratings",
    body,
    idempotencyKey,
    schema: ratingEnvelopeSchema,
  });
}

/** RATE-002 · Ratings the caller can see through their order or complaint, newest first. */
export async function listRatings(
  params: RatingListParams & { readonly cursor: string | null },
  signal?: AbortSignal,
): Promise<RatingPage> {
  const page = await apiRequest({
    dataId: "RATE-002",
    logger: log,
    fn: "listRatings",
    path: "/ratings",
    query: {
      target: params.target,
      sales_order_id: params.salesOrderId,
      complaint_id: params.complaintId,
      partner_id: params.partnerId,
      max_score: params.maxScore,
      limit: RATING_PAGE_SIZE,
      cursor: params.cursor,
    },
    schema: ratingPageSchema,
    signal,
  });
  if (page.skipped > 0) {
    log.warn(
      "listRatings",
      `left out ${String(page.skipped)} row(s) that did not match the contract`,
      {
        dataId: "RATE-002",
        context: { skipped: page.skipped, kept: page.items.length },
      },
    );
  }
  return page;
}

/** RATE-003 · Count, average and low ratings by dealer, product or kind; lowest average first. */
export function getRatingSummary(
  groupBy: RatingSummaryGroup,
  signal?: AbortSignal,
): Promise<RatingSummaryRow[]> {
  return apiRequest({
    dataId: "RATE-003",
    logger: log,
    fn: "getRatingSummary",
    path: "/ratings/summary",
    query: { group_by: groupBy },
    schema: ratingSummarySchema,
    signal,
  });
}

/** RATE-004 · A dealer's derived rating today. 403 `rating_not_permitted` without payments.view. */
export function getDealerRating(partnerId: string, signal?: AbortSignal): Promise<DealerRating> {
  return apiRequest({
    dataId: "RATE-004",
    logger: log,
    fn: "getDealerRating",
    path: `/partners/${encodeURIComponent(partnerId)}/dealer-rating`,
    schema: dealerRatingSchema,
    signal,
  });
}
