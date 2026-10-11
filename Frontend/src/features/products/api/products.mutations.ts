"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import {
  assignHsn,
  closePriceList,
  createPriceList,
  createProduct,
  patchProduct,
  publishPriceList,
  readAllRates,
  replaceRates,
  setTaxRate,
} from "./products.api";
import { productKeys } from "./products.queries";
import type { PriceList, Product } from "./products.schemas";

/** Everything in the product master; the quotation picker reads products by its own key. */
function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: productKeys.all });
  };
}

/** MSTR-004 · Add a product. */
export function useCreateProduct(): UseMutationResult<
  Product,
  Error,
  Parameters<typeof createProduct>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "create-product"],
    mutationFn: createProduct,
    meta: { dataId: "MSTR-004" },
    onSuccess: refresh,
  });
}

/** MSTR-004 · Correct a product, or switch it off or on. */
export function usePatchProduct(): UseMutationResult<
  Product,
  Error,
  Parameters<typeof patchProduct>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "patch-product"],
    mutationFn: patchProduct,
    meta: { dataId: "MSTR-004" },
    onSuccess: refresh,
  });
}

/** MSTR-005 · Classify a product under a code, from a date. */
export function useAssignHsn(): UseMutationResult<
  Awaited<ReturnType<typeof assignHsn>>,
  Error,
  Parameters<typeof assignHsn>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "hsn"],
    mutationFn: assignHsn,
    meta: { dataId: "MSTR-005" },
    onSuccess: refresh,
  });
}

/** MSTR-005 · A code's slab, from a date. */
export function useSetTaxRate(): UseMutationResult<
  Awaited<ReturnType<typeof setTaxRate>>,
  Error,
  Parameters<typeof setTaxRate>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "tax-rate"],
    mutationFn: setTaxRate,
    meta: { dataId: "MSTR-005" },
    onSuccess: refresh,
  });
}

/** MSTR-006 · Start a price list (a draft). */
export function useCreatePriceList(): UseMutationResult<
  PriceList,
  Error,
  Parameters<typeof createPriceList>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "create-list"],
    mutationFn: createPriceList,
    meta: { dataId: "MSTR-006" },
    onSuccess: refresh,
  });
}

/**
 * MSTR-006 · Save rate changes on a draft. `PUT /items` replaces every rate, so the list's own
 * rates are read first and the edits laid over them: a rate typed is set, a rate cleared is
 * removed, and every other rate stays as it was.
 */
export function useSaveRates(): UseMutationResult<
  Awaited<ReturnType<typeof replaceRates>>,
  Error,
  { listId: string; edits: ReadonlyMap<string, string>; idempotencyKey: string }
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "rates"],
    mutationFn: async ({ listId, edits, idempotencyKey }) => {
      const rates = await readAllRates(listId);
      for (const [productId, rate] of edits) {
        if (rate.trim() === "") rates.delete(productId);
        else rates.set(productId, rate.trim());
      }
      return replaceRates({ listId, rates, idempotencyKey });
    },
    meta: { dataId: "MSTR-006" },
    onSuccess: refresh,
  });
}

/**
 * MSTR-006 · Start a new list from another's rates: a draft with the same scope, filled with a
 * copy of every rate. A published list is never edited; this is how it is corrected.
 */
export function useCopyPriceList(): UseMutationResult<
  PriceList,
  Error,
  {
    source: PriceList;
    name: string;
    from: string;
    sourceNote: string | null;
    createKey: string;
    fillKey: string;
  }
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "copy-list"],
    mutationFn: async ({ source, name, from, sourceNote, createKey, fillKey }) => {
      const draft = await createPriceList({
        body: {
          name,
          effective_from: from,
          state_territory_id: source.state?.id ?? null,
          channel_tier: source.tier,
          effective_to: null,
          source_note: sourceNote,
        },
        idempotencyKey: createKey,
      });
      const rates = await readAllRates(source.id);
      if (rates.size > 0) await replaceRates({ listId: draft.id, rates, idempotencyKey: fillKey });
      return draft;
    },
    meta: { dataId: "MSTR-006" },
    onSuccess: refresh,
  });
}

/** MSTR-006 · Put a draft into force. */
export function usePublishPriceList(): UseMutationResult<
  { closedPredecessorId: string | null },
  Error,
  Parameters<typeof publishPriceList>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "publish"],
    mutationFn: publishPriceList,
    meta: { dataId: "MSTR-006" },
    onSuccess: refresh,
  });
}

/** MSTR-006 · Close a list from a date. */
export function useClosePriceList(): UseMutationResult<
  PriceList,
  Error,
  Parameters<typeof closePriceList>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...productKeys.all, "close"],
    mutationFn: closePriceList,
    meta: { dataId: "MSTR-006" },
    onSuccess: refresh,
  });
}
