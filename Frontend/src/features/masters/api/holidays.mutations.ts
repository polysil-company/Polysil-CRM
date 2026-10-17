"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { addHoliday, removeHoliday } from "./holidays.api";
import { holidayKeys } from "./holidays.queries";
import type { AddHolidayRequest, Holiday } from "./holidays.schemas";

/** MSTR-019 · Add a holiday; refreshes every year's list. */
export function useAddHoliday(): UseMutationResult<
  Holiday,
  Error,
  { readonly body: AddHolidayRequest; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...holidayKeys.all, "add"],
    mutationFn: addHoliday,
    meta: { dataId: "MSTR-019" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: holidayKeys.all });
    },
  });
}

/** MSTR-019 · Remove a future holiday; refreshes every year's list. */
export function useRemoveHoliday(): UseMutationResult<
  void,
  Error,
  { readonly day: string; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...holidayKeys.all, "remove"],
    mutationFn: removeHoliday,
    meta: { dataId: "MSTR-019" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: holidayKeys.all });
    },
  });
}
