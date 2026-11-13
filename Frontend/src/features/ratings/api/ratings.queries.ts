import { infiniteQueryOptions, queryOptions } from "@tanstack/react-query";

import { getDealerRating, getRatingSummary, listRatings } from "./ratings.api";
import type { RatingListParams, RatingSummaryGroup } from "./ratings.schemas";

/** The first page: no cursor yet. */
const FIRST_PAGE: string | null = null;

/** Query keys for ratings. `ratingKeys.all` covers the lists, summaries and dealer cards. */
export const ratingKeys = {
  all: ["ratings"] as const,
  lists: () => [...ratingKeys.all, "list"] as const,
  list: (params: RatingListParams) => [...ratingKeys.lists(), params] as const,
  summary: (groupBy: RatingSummaryGroup) => [...ratingKeys.all, "summary", groupBy] as const,
  dealer: (partnerId: string) => [...ratingKeys.all, "dealer", partnerId] as const,
};

/** RATE-002 · A page of ratings at a time. */
export function ratingListQueryOptions(params: RatingListParams) {
  return infiniteQueryOptions({
    queryKey: ratingKeys.list(params),
    queryFn: ({ pageParam, signal }) => listRatings({ ...params, cursor: pageParam }, signal),
    initialPageParam: FIRST_PAGE,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    meta: { dataId: "RATE-002" },
  });
}

/** RATE-003 · The summary by one grouping. */
export function ratingSummaryQueryOptions(groupBy: RatingSummaryGroup) {
  return queryOptions({
    queryKey: ratingKeys.summary(groupBy),
    queryFn: ({ signal }) => getRatingSummary(groupBy, signal),
    meta: { dataId: "RATE-003" },
  });
}

/** RATE-004 · One dealer's rating. A 403 is an answer, not a failure worth retrying. */
export function dealerRatingQueryOptions(partnerId: string) {
  return queryOptions({
    queryKey: ratingKeys.dealer(partnerId),
    queryFn: ({ signal }) => getDealerRating(partnerId, signal),
    meta: { dataId: "RATE-004" },
  });
}
