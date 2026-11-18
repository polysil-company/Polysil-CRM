"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createMatrix, reviseMaster } from "./subsidy-masters.api";
import { subsidyMasterKeys } from "./subsidy-masters.queries";
import type { MasterKind, RevisionResult } from "./subsidy-masters.schemas";
import { subsidyKeys } from "./subsidy.queries";

/** The masters and everything calculated from them refresh after a revision. */
function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: subsidyMasterKeys.all });
    void queryClient.invalidateQueries({ queryKey: subsidyKeys.all });
  };
}

/** SUBS-012 · Revise one master's rows from a date. */
export function useReviseMaster<K extends MasterKind>(): UseMutationResult<
  RevisionResult,
  Error,
  Parameters<typeof reviseMaster<K>>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...subsidyMasterKeys.all, "revise"],
    mutationFn: reviseMaster<K>,
    meta: { dataId: "SUBS-012" },
    onSuccess: refresh,
  });
}

/** SUBS-013 · A new matrix from a date. */
export function useCreateMatrix(): UseMutationResult<
  RevisionResult,
  Error,
  Parameters<typeof createMatrix>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...subsidyMasterKeys.all, "matrix"],
    mutationFn: createMatrix,
    meta: { dataId: "SUBS-013" },
    onSuccess: refresh,
  });
}
