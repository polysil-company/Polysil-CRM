"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { setWarrantyTerm } from "./warranty.api";
import { warrantyKeys } from "./warranty.queries";
import type { SetWarrantyTermRequest, WarrantyTerm } from "./warranty.schemas";

/** MSTR-017 · Set a warranty period from a date; refreshes the terms and every order's warranty. */
export function useSetWarrantyTerm(): UseMutationResult<
  WarrantyTerm[],
  Error,
  { readonly body: SetWarrantyTermRequest; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...warrantyKeys.all, "set-term"],
    mutationFn: setWarrantyTerm,
    meta: { dataId: "MSTR-017" },
    onSuccess: (terms) => {
      queryClient.setQueryData(warrantyKeys.terms(), terms);
      void queryClient.invalidateQueries({ queryKey: warrantyKeys.all });
    },
  });
}
