"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createScheme, patchScheme } from "./schemes.api";
import { schemeKeys } from "./schemes.queries";
import type { Scheme } from "./schemes.schemas";

function useRefresh(): (scheme: Scheme) => void {
  const queryClient = useQueryClient();
  return (scheme) => {
    queryClient.setQueryData(schemeKeys.detail(scheme.id), scheme);
    void queryClient.invalidateQueries({ queryKey: [...schemeKeys.all, "list"] });
  };
}

/** SCHM-002 · Create a scheme. */
export function useCreateScheme(): UseMutationResult<
  Scheme,
  Error,
  Parameters<typeof createScheme>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...schemeKeys.all, "create"],
    mutationFn: createScheme,
    meta: { dataId: "SCHM-002" },
    onSuccess: refresh,
  });
}

/** SCHM-002 · Change a scheme, or switch it off or on. */
export function usePatchScheme(): UseMutationResult<
  Scheme,
  Error,
  Parameters<typeof patchScheme>[0]
> {
  const refresh = useRefresh();
  return useMutation({
    mutationKey: [...schemeKeys.all, "patch"],
    mutationFn: patchScheme,
    meta: { dataId: "SCHM-002" },
    onSuccess: refresh,
  });
}
