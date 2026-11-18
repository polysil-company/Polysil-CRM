"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { applicationKeys } from "./subsidy-applications.queries";
import { createScheme, patchScheme, renameStage } from "./subsidy-schemes.api";
import { schemeKeys } from "./subsidy-schemes.queries";
import type { SchemeDetail } from "./subsidy-schemes.schemas";

function useRefresh(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: schemeKeys.all });
    // A lead's scheme, and a scheme's stage names, follow these.
    void queryClient.invalidateQueries({ queryKey: applicationKeys.all });
  };
}

/** SUBS-014 · Set up another state's scheme. */
export function useCreateScheme(): UseMutationResult<
  SchemeDetail,
  Error,
  Parameters<typeof createScheme>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...schemeKeys.all, "create"],
    mutationFn: createScheme,
    meta: { dataId: "SUBS-014" },
    onSuccess: refresh,
  });
}

/** SUBS-014 · Rename, switch off or on, or link a scheme to its state. */
export function usePatchScheme(): UseMutationResult<
  SchemeDetail,
  Error,
  Parameters<typeof patchScheme>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...schemeKeys.all, "patch"],
    mutationFn: patchScheme,
    meta: { dataId: "SUBS-014" },
    onSuccess: refresh,
  });
}

/** SUBS-014 · Rename a stage. */
export function useRenameStage(): UseMutationResult<
  void,
  Error,
  Parameters<typeof renameStage>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...schemeKeys.all, "stage"],
    mutationFn: renameStage,
    meta: { dataId: "SUBS-014" },
    onSuccess: refresh,
  });
}
