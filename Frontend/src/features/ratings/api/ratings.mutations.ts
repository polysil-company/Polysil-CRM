"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createRating } from "./ratings.api";
import { ratingKeys } from "./ratings.queries";
import type { Rating, RatingCreateRequest } from "./ratings.schemas";

/** RATE-001 · Record a rating; refreshes every ratings list, summary and dealer card. */
export function useCreateRating(): UseMutationResult<
  Rating,
  Error,
  { readonly body: RatingCreateRequest; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...ratingKeys.all, "create"],
    mutationFn: createRating,
    meta: { dataId: "RATE-001" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ratingKeys.all });
    },
  });
}
