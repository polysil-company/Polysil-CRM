"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { sessionKeys } from "@/features/session/api/session.queries";

import { putEmailPreferences } from "./auth.api";

/** AUTH-008 · Save the two email switches; the session reads them again. */
export function useEmailPreferences(): UseMutationResult<
  Awaited<ReturnType<typeof putEmailPreferences>>,
  Error,
  Parameters<typeof putEmailPreferences>[0]
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["email-preferences"],
    mutationFn: putEmailPreferences,
    meta: { dataId: "AUTH-008" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: sessionKeys.all });
    },
  });
}
