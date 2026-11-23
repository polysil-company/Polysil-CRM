"use client";

import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";

import { createQrCode, patchQrCode } from "./lead-capture.api";
import { leadCaptureKeys } from "./lead-capture.queries";
import type { QrCode } from "./lead-capture.schemas";

/** LEAD-013 · A new code; the list refetches with it at the top. */
export function useCreateQrCode(): UseMutationResult<
  QrCode,
  Error,
  Parameters<typeof createQrCode>[0]
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...leadCaptureKeys.qrCodes(), "create"],
    mutationFn: createQrCode,
    meta: { dataId: "LEAD-013" },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: leadCaptureKeys.qrCodes() });
    },
  });
}

/** LEAD-013 · Rename, re-point or switch off a code; the row updates in place. */
export function usePatchQrCode(): UseMutationResult<
  QrCode,
  Error,
  Parameters<typeof patchQrCode>[0]
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: [...leadCaptureKeys.qrCodes(), "patch"],
    mutationFn: patchQrCode,
    meta: { dataId: "LEAD-013" },
    onSuccess: (saved) => {
      queryClient.setQueryData(leadCaptureKeys.qrCodes(), (rows: QrCode[] | undefined) =>
        rows?.map((row) => (row.id === saved.id ? saved : row)),
      );
    },
  });
}
