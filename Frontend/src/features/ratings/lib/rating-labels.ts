import type {
  RatedBy,
  RatingSummaryGroup,
  RatingTarget,
} from "@/features/ratings/api/ratings.schemas";
import { isApiError } from "@/lib/api/errors";

/** RATE-001 … RATE-003 · What ratings say on screen. */

export const RATING_TARGET_LABELS: Readonly<Record<RatingTarget, string>> = {
  installation: "Installation",
  service: "Service",
  product: "Product",
};

export const RATED_BY_LABELS: Readonly<Record<RatedBy, string>> = {
  customer: "Customer",
  dealer: "Dealer",
};

export const SUMMARY_GROUP_LABELS: Readonly<Record<RatingSummaryGroup, string>> = {
  partner: "By dealer",
  product: "By product",
  target: "By kind",
};

/** The words for each score, so the stars never carry the meaning alone. */
export const SCORE_LABELS: Readonly<Record<number, string>> = {
  1: "Very poor",
  2: "Poor",
  3: "Fair",
  4: "Good",
  5: "Very good",
};

/** "1 star", "4 stars". */
export function starsText(score: number): string {
  return score === 1 ? "1 star" : `${String(score)} stars`;
}

/** An average to one decimal, as "4.3". */
export function averageText(average: number): string {
  return (Math.round(average * 10) / 10).toFixed(1);
}

/**
 * Who records a rating from this account: staff record what the farmer said ("customer"), a
 * dealer's user rates for its firm ("dealer").
 */
export function raterKindOf(isStaff: boolean): RatedBy {
  return isStaff ? "customer" : "dealer";
}

/** A refusal from `POST /ratings` in words, or null when it is something else. */
export function ratingRefusal(error: unknown): string | null {
  if (!isApiError(error)) return null;
  switch (error.code) {
    case "not_rateable":
      return error.message || "This can't be rated yet.";
    case "product_not_shipped":
      return "This product hasn't shipped on this order yet.";
    case "rating_exists":
      return "This has been rated already. A rating is never changed.";
    case "not_your_order":
      return "A dealer rates only its own orders and complaints.";
    default:
      return null;
  }
}
