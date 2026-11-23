"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createWarehouse, patchWarehouse, recordStock, type WriteInput } from "./stock.api";
import { stockKeys } from "./stock.queries";
import type { RecordStockRequest, Recorded, Warehouse, WarehouseRequest } from "./stock.schemas";

function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: stockKeys.all });
  };
}

/** MSTR-015 · Record stock received, or a correction. */
export function useRecordStock(): UseMutationResult<
  Recorded,
  Error,
  WriteInput<RecordStockRequest>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...stockKeys.all, "record"],
    mutationFn: recordStock,
    meta: { dataId: "MSTR-015" },
    onSuccess: refresh,
  });
}

/** MSTR-016 · Add a warehouse. */
export function useCreateWarehouse(): UseMutationResult<
  Warehouse,
  Error,
  WriteInput<WarehouseRequest>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...stockKeys.all, "create-warehouse"],
    mutationFn: createWarehouse,
    meta: { dataId: "MSTR-016" },
    onSuccess: refresh,
  });
}

/** MSTR-016 · Change a warehouse, make it the default, or switch it off. */
export function usePatchWarehouse(): UseMutationResult<
  Warehouse,
  Error,
  { readonly warehouseId: string } & WriteInput<Partial<WarehouseRequest>>
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...stockKeys.all, "patch-warehouse"],
    mutationFn: ({ warehouseId, ...input }) => patchWarehouse(warehouseId, input),
    meta: { dataId: "MSTR-016" },
    onSuccess: refresh,
  });
}
