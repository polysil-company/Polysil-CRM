import { queryOptions } from "@tanstack/react-query";

import { listMaster, listQuantityMatrices, listUnitCostMatrices } from "./subsidy-masters.api";
import type { MasterKind } from "./subsidy-masters.schemas";

export const subsidyMasterKeys = {
  all: ["subsidy-masters"] as const,
  rows: (kind: MasterKind, scheme: string, on: string | null) =>
    [...subsidyMasterKeys.all, "rows", kind, scheme, on] as const,
  matrices: (kind: "unit-cost" | "quantity", scheme: string, on: string | null) =>
    [...subsidyMasterKeys.all, "matrices", kind, scheme, on] as const,
};

/** SUBS-012 · One master's rows in force on a date. */
export function masterRowsQueryOptions<K extends MasterKind>(
  kind: K,
  scheme: string,
  on: string | null,
) {
  return queryOptions({
    queryKey: subsidyMasterKeys.rows(kind, scheme, on),
    queryFn: ({ signal }) => listMaster(kind, scheme, on, signal),
    meta: { dataId: "SUBS-012" },
  });
}

/** SUBS-013 · The unit-cost matrices in force on a date. */
export function unitCostMatricesQueryOptions(scheme: string, on: string | null) {
  return queryOptions({
    queryKey: subsidyMasterKeys.matrices("unit-cost", scheme, on),
    queryFn: ({ signal }) => listUnitCostMatrices(scheme, on, signal),
    meta: { dataId: "SUBS-013" },
  });
}

/** SUBS-013 · The quantity matrices in force on a date. */
export function quantityMatricesQueryOptions(scheme: string, on: string | null) {
  return queryOptions({
    queryKey: subsidyMasterKeys.matrices("quantity", scheme, on),
    queryFn: ({ signal }) => listQuantityMatrices(scheme, on, signal),
    meta: { dataId: "SUBS-013" },
  });
}
