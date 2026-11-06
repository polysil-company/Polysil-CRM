"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import {
  actOnMarketingOrder,
  createMarketingOrder,
  createMaterial,
  dispatchMarketingOrder,
  patchMaterial,
  type WriteInput,
} from "./marketing.api";
import { marketingKeys } from "./marketing.queries";
import type {
  DispatchRequest,
  MarketingAction,
  MarketingOrder,
  MarketingOrderCreateRequest,
  Material,
  MaterialCreateRequest,
  MaterialPatchRequest,
} from "./marketing.schemas";

/** Every write refreshes the whole feature: lists, orders and the catalogue are small. */
function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: marketingKeys.all });
  };
}

/** MKT-002 · Add a catalogue item. */
export function useCreateMaterial(): UseMutationResult<
  Material,
  Error,
  WriteInput<MaterialCreateRequest>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...marketingKeys.all, "create-material"],
    mutationFn: createMaterial,
    meta: { dataId: "MKT-002" },
    onSuccess: refresh,
  });
}

/** MKT-002 · Change a catalogue item, or switch it off. */
export function usePatchMaterial(): UseMutationResult<
  Material,
  Error,
  { readonly materialId: string } & WriteInput<MaterialPatchRequest>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...marketingKeys.all, "patch-material"],
    mutationFn: ({ materialId, ...input }) => patchMaterial(materialId, input),
    meta: { dataId: "MKT-002" },
    onSuccess: refresh,
  });
}

/** MKT-003 · Place an order. */
export function useCreateMarketingOrder(): UseMutationResult<
  MarketingOrder,
  Error,
  WriteInput<MarketingOrderCreateRequest>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...marketingKeys.all, "create-order"],
    mutationFn: createMarketingOrder,
    meta: { dataId: "MKT-003" },
    onSuccess: refresh,
  });
}

/** MKT-004 · Approve, reject or cancel. */
export function useActOnMarketingOrder(): UseMutationResult<
  MarketingOrder,
  Error,
  { readonly orderId: string; readonly action: MarketingAction } & WriteInput<{
    readonly remark: string | null;
  }>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...marketingKeys.all, "act"],
    mutationFn: ({ orderId, action, ...input }) => actOnMarketingOrder(orderId, action, input),
    meta: { dataId: "MKT-004" },
    onSuccess: refresh,
  });
}

/** MKT-004 · Record the dispatch. */
export function useDispatchMarketingOrder(): UseMutationResult<
  MarketingOrder,
  Error,
  { readonly orderId: string } & WriteInput<DispatchRequest>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...marketingKeys.all, "dispatch"],
    mutationFn: ({ orderId, ...input }) => dispatchMarketingOrder(orderId, input),
    meta: { dataId: "MKT-004" },
    onSuccess: refresh,
  });
}
