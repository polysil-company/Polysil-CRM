"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { endDuty, startDuty } from "./duty.api";
import type { Duty, DutyEndRequest, DutyStartRequest } from "./duty.schemas";
import { trackingKeys } from "./tracking.queries";
import { visitKeys } from "./visits.queries";

interface DutyInput<TBody> {
  readonly body: TBody;
  readonly idempotencyKey: string;
}

/** After going on or off duty: the config's open duty, the team map and today's route. */
function useRefreshDuty(): () => void {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: visitKeys.config() });
    void queryClient.invalidateQueries({ queryKey: trackingKeys.all });
  };
}

/** TRK-008 · Go on duty. */
export function useStartDuty(): UseMutationResult<Duty, Error, DutyInput<DutyStartRequest>> {
  const refresh = useRefreshDuty();
  return useMutation({
    mutationKey: [...trackingKeys.all, "duty", "start"],
    mutationFn: startDuty,
    meta: { dataId: "TRK-008" },
    onSuccess: refresh,
  });
}

/** TRK-008 · Go off duty. */
export function useEndDuty(): UseMutationResult<Duty, Error, DutyInput<DutyEndRequest>> {
  const refresh = useRefreshDuty();
  return useMutation({
    mutationKey: [...trackingKeys.all, "duty", "end"],
    mutationFn: endDuty,
    meta: { dataId: "TRK-008" },
    onSuccess: refresh,
  });
}
