"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { addLut, deleteLut } from "./seller-gstins.api";
import { sellerGstinKeys } from "./seller-gstins.queries";
import type { AddLutRequest, Lut } from "./seller-gstins.schemas";

/** MSTR-018 · Record a LUT; refreshes the registrations. */
export function useAddLut(): UseMutationResult<
  Lut,
  Error,
  { readonly gstinId: string; readonly body: AddLutRequest; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...sellerGstinKeys.all, "add-lut"],
    mutationFn: addLut,
    meta: { dataId: "MSTR-018" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: sellerGstinKeys.all });
    },
  });
}

/** MSTR-018 · Remove a LUT no document carries; refreshes the registrations. */
export function useDeleteLut(): UseMutationResult<
  void,
  Error,
  { readonly gstinId: string; readonly lutId: string; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...sellerGstinKeys.all, "delete-lut"],
    mutationFn: deleteLut,
    meta: { dataId: "MSTR-018" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: sellerGstinKeys.all });
    },
  });
}
