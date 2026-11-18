"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { orderKeys } from "@/features/orders/api/orders.queries";

import {
  allocatePayment,
  putPaymentSchedule,
  recordPayment,
  voidPayment,
  type WriteInput,
} from "./payments.api";
import { paymentKeys } from "./payments.queries";
import type {
  AllocationRequest,
  OrderPayments,
  Payment,
  RecordPaymentRequest,
  ScheduleRequest,
} from "./payments.schemas";

/** Money moved: refresh the receipts, ledgers, credit, and every order (balances and lists). */
function useRefreshMoney(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    void queryClient.invalidateQueries({ queryKey: orderKeys.all });
  };
}

/** ACCT-002 · Record a payment. */
export function useRecordPayment(): UseMutationResult<
  Payment,
  Error,
  WriteInput<RecordPaymentRequest>
> {
  const refresh = useRefreshMoney();
  return useMutation({
    mutationKey: [...paymentKeys.all, "record"],
    mutationFn: recordPayment,
    meta: { dataId: "ACCT-002" },
    onSuccess: refresh,
  });
}

/** ACCT-003 · Allocate what is left of a receipt. */
export function useAllocatePayment(): UseMutationResult<
  Payment,
  Error,
  { paymentId: string } & WriteInput<{ readonly allocations: readonly AllocationRequest[] }>
> {
  const refresh = useRefreshMoney();
  return useMutation({
    mutationKey: [...paymentKeys.all, "allocate"],
    mutationFn: ({ paymentId, ...input }) => allocatePayment(paymentId, input),
    meta: { dataId: "ACCT-003" },
    onSuccess: refresh,
  });
}

/** ACCT-003 · Void a receipt. */
export function useVoidPayment(): UseMutationResult<
  Payment,
  Error,
  { paymentId: string } & WriteInput<{ readonly reason: string }>
> {
  const refresh = useRefreshMoney();
  return useMutation({
    mutationKey: [...paymentKeys.all, "void"],
    mutationFn: ({ paymentId, ...input }) => voidPayment(paymentId, input),
    meta: { dataId: "ACCT-003" },
    onSuccess: refresh,
  });
}

/** ACCT-004 · Replace an order's instalment plan. */
export function useSavePaymentSchedule(): UseMutationResult<
  OrderPayments,
  Error,
  { orderId: string } & WriteInput<ScheduleRequest>
> {
  const refresh = useRefreshMoney();
  return useMutation({
    mutationKey: [...paymentKeys.all, "schedule"],
    mutationFn: ({ orderId, ...input }) => putPaymentSchedule(orderId, input),
    meta: { dataId: "ACCT-004" },
    onSuccess: refresh,
  });
}
