"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { approvalKeys } from "@/features/approvals/api/approvals.queries";
import { leadKeys } from "@/features/leads/api/leads.queries";
import { quotationKeys } from "@/features/quotations/api/quotations.queries";

import {
  cancelOrder,
  closeOrderShort,
  createDispatch,
  createOrder,
  deleteOrder,
  patchOrder,
  submitOrder,
  voidDispatch,
  type WriteInput,
} from "./orders.api";
import { orderKeys } from "./orders.queries";
import type {
  CreateDispatchRequest,
  CreateOrderFromQuotations,
  Dispatch,
  ExpectedStatusRequest,
  Order,
  PatchOrderRequest,
  RemarkRequest,
} from "./orders.schemas";

/** An action on one order (or one of its dispatches), with its body and retry-safe key. */
export interface OrderActionInput<TBody> {
  readonly id: string;
  readonly input: WriteInput<TBody>;
}

/**
 * An order the backend just wrote: its document is the answer, and everything that shows it
 * refetches — the lists, its history, the approvals inbox (a submit or a cancel changes the
 * queue), the lead, and the quotations it was made from.
 */
function useApplyOrder(): (order: Order) => void {
  const queryClient = useQueryClient();
  return (order) => {
    queryClient.setQueryData(orderKeys.detail(order.id), order);
    void queryClient.invalidateQueries({ queryKey: orderKeys.lists() });
    void queryClient.invalidateQueries({ queryKey: orderKeys.timelines() });
    void queryClient.invalidateQueries({ queryKey: approvalKeys.all });
    if (order.lead !== null) {
      void queryClient.invalidateQueries({ queryKey: leadKeys.detail(order.lead.id) });
    }
    for (const quotation of order.quotations) {
      void queryClient.invalidateQueries({ queryKey: quotationKeys.detail(quotation.id) });
    }
  };
}

/** SO-003 · A draft from accepted quotations. */
export function useCreateOrder(): UseMutationResult<
  Order,
  Error,
  WriteInput<CreateOrderFromQuotations>
> {
  const apply = useApplyOrder();
  return useMutation({
    mutationKey: [...orderKeys.all, "create"],
    mutationFn: createOrder,
    meta: { dataId: "SO-003" },
    onSuccess: apply,
  });
}

/** SO-003 · A draft's header. */
export function usePatchOrder(): UseMutationResult<
  Order,
  Error,
  OrderActionInput<PatchOrderRequest>
> {
  const apply = useApplyOrder();
  return useMutation({
    mutationKey: [...orderKeys.all, "patch"],
    mutationFn: ({ id, input }) => patchOrder(id, input),
    meta: { dataId: "SO-003" },
    onSuccess: apply,
  });
}

/** SO-003 · Delete a draft never submitted. The page leaves it, so only the lists refetch. */
export function useDeleteOrder(): UseMutationResult<
  void,
  Error,
  { id: string; idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...orderKeys.all, "delete"],
    mutationFn: ({ id, idempotencyKey }) => deleteOrder(id, idempotencyKey),
    meta: { dataId: "SO-003" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: orderKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: quotationKeys.all });
    },
  });
}

/** SO-004 · Submit for approval. */
export function useSubmitOrder(): UseMutationResult<
  Order,
  Error,
  OrderActionInput<ExpectedStatusRequest>
> {
  const apply = useApplyOrder();
  return useMutation({
    mutationKey: [...orderKeys.all, "submit"],
    mutationFn: ({ id, input }) => submitOrder(id, input),
    meta: { dataId: "SO-004" },
    onSuccess: apply,
  });
}

/** SO-004 · Cancel, with a reason. */
export function useCancelOrder(): UseMutationResult<Order, Error, OrderActionInput<RemarkRequest>> {
  const apply = useApplyOrder();
  return useMutation({
    mutationKey: [...orderKeys.all, "cancel"],
    mutationFn: ({ id, input }) => cancelOrder(id, input),
    meta: { dataId: "SO-004" },
    onSuccess: apply,
  });
}

/** DISP-002 · Record what left; the order is re-read for its new quantities and status. */
export function useCreateDispatch(): UseMutationResult<
  Dispatch,
  Error,
  OrderActionInput<CreateDispatchRequest>
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...orderKeys.all, "dispatch"],
    mutationFn: ({ id, input }) => createDispatch(id, input),
    meta: { dataId: "DISP-002" },
    onSuccess: (dispatch) => {
      void queryClient.invalidateQueries({ queryKey: orderKeys.detail(dispatch.orderId) });
      void queryClient.invalidateQueries({ queryKey: orderKeys.lists() });
      void queryClient.invalidateQueries({ queryKey: orderKeys.timelines() });
    },
  });
}

/** DISP-002 · Void a dispatch (its id), with a reason. */
export function useVoidDispatch(): UseMutationResult<
  Order,
  Error,
  OrderActionInput<RemarkRequest>
> {
  const apply = useApplyOrder();
  return useMutation({
    mutationKey: [...orderKeys.all, "void"],
    mutationFn: ({ id, input }) => voidDispatch(id, input),
    meta: { dataId: "DISP-002" },
    onSuccess: apply,
  });
}

/** DISP-002 · Close the rest short, with a reason. */
export function useCloseOrderShort(): UseMutationResult<
  Order,
  Error,
  OrderActionInput<RemarkRequest>
> {
  const apply = useApplyOrder();
  return useMutation({
    mutationKey: [...orderKeys.all, "close-short"],
    mutationFn: ({ id, input }) => closeOrderShort(id, input),
    meta: { dataId: "DISP-002" },
    onSuccess: apply,
  });
}
