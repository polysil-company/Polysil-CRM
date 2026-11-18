"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { patchCustomer } from "./customers.api";
import { customerKeys } from "./customers.queries";
import type { CustomerDetail, CustomerPatchRequest } from "./customers.schemas";

/** LEAD-018 · Edit a customer or its consent; refreshes the page, its timeline and the lists. */
export function usePatchCustomer(): UseMutationResult<
  CustomerDetail,
  Error,
  {
    readonly customerId: string;
    readonly body: CustomerPatchRequest;
    readonly idempotencyKey: string;
  }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...customerKeys.all, "patch"],
    mutationFn: patchCustomer,
    meta: { dataId: "LEAD-018" },
    onSuccess: (customer) => {
      queryClient.setQueryData(customerKeys.detail(customer.id), customer);
      void queryClient.invalidateQueries({ queryKey: customerKeys.timeline(customer.id) });
      void queryClient.invalidateQueries({ queryKey: customerKeys.lists() });
    },
  });
}
