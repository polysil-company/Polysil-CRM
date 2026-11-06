"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { patchSettings } from "./settings.api";
import { settingKeys } from "./settings.queries";
import type { Setting, SettingsPatchRequest } from "./settings.schemas";

/** ADMN-007 · Change some settings. The answer is the full list: it replaces the cached one. */
export function usePatchSettings(): UseMutationResult<Setting[], Error, SettingsPatchRequest> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...settingKeys.all, "patch"],
    mutationFn: patchSettings,
    meta: { dataId: "ADMN-007" },
    onSuccess: (settings) => {
      queryClient.setQueryData(settingKeys.all, settings);
    },
  });
}
