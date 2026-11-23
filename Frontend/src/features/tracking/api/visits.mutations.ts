"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { trackingKeys } from "./tracking.queries";
import type { Visit } from "./tracking.schemas";
import { acceptTrackingConsent, checkIn, checkOut, uploadVisitPhoto } from "./visits.api";
import { visitKeys } from "./visits.queries";
import type { CheckInRequest, CheckOutRequest, VisitPhoto } from "./visits.schemas";

/** After a visit changes: my visits, the visit itself, and the team map and routes. */
function useRefreshVisits(): (visit?: Visit) => void {
  const queryClient = useQueryClient();
  return (visit) => {
    if (visit !== undefined) queryClient.setQueryData(visitKeys.detail(visit.id), visit);
    void queryClient.invalidateQueries({ queryKey: trackingKeys.all });
  };
}

/** TRK-003 · Accept the tracking consent. */
export function useAcceptConsent(): UseMutationResult<
  null,
  Error,
  { readonly version: string; readonly idempotencyKey: string }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...visitKeys.all, "consent"],
    mutationFn: acceptTrackingConsent,
    meta: { dataId: "TRK-003" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: visitKeys.config() });
    },
  });
}

/** TRK-003 · Check in. */
export function useCheckIn(): UseMutationResult<
  Visit,
  Error,
  { readonly body: CheckInRequest; readonly idempotencyKey: string }
> {
  const refresh = useRefreshVisits();
  return useMutation({
    mutationKey: [...visitKeys.all, "check-in"],
    mutationFn: checkIn,
    meta: { dataId: "TRK-003" },
    onSuccess: refresh,
  });
}

/** TRK-004 · Check out. */
export function useCheckOut(): UseMutationResult<
  Visit,
  Error,
  { readonly visitId: string; readonly body: CheckOutRequest; readonly idempotencyKey: string }
> {
  const refresh = useRefreshVisits();
  return useMutation({
    mutationKey: [...visitKeys.all, "check-out"],
    mutationFn: checkOut,
    meta: { dataId: "TRK-004" },
    onSuccess: refresh,
  });
}

/** TRK-004 · Add a photo to a visit. */
export function useUploadVisitPhoto(): UseMutationResult<
  VisitPhoto,
  Error,
  {
    readonly visitId: string;
    readonly file: Blob & { readonly name: string };
    readonly idempotencyKey: string;
  }
> {
  const refresh = useRefreshVisits();
  return useMutation({
    mutationKey: [...visitKeys.all, "photo"],
    mutationFn: uploadVisitPhoto,
    meta: { dataId: "TRK-004" },
    onSuccess: () => {
      refresh();
    },
  });
}
