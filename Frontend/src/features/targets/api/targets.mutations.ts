"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { setTargets } from "./targets.api";
import { targetKeys } from "./targets.queries";
import type { PersonTargets, SetTargetsRequest } from "./targets.schemas";

/** TGT-002 · Set a person's targets; the answer is their targets, and achievement refreshes. */
export function useSetTargets(): UseMutationResult<
  PersonTargets,
  Error,
  { body: SetTargetsRequest; idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...targetKeys.all, "set"],
    mutationFn: setTargets,
    meta: { dataId: "TGT-002" },
    onSuccess: (targets) => {
      queryClient.setQueryData(targetKeys.person(targets.user.id, targets.month), targets);
      void queryClient.invalidateQueries({ queryKey: targetKeys.achievement(targets.month) });
    },
  });
}
