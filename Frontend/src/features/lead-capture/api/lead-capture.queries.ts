import { queryOptions } from "@tanstack/react-query";

import { getPublicLeadForm, listPublicTerritories, listQrCodes } from "./lead-capture.api";

export const leadCaptureKeys = {
  all: ["lead-capture"] as const,
  qrCodes: () => [...leadCaptureKeys.all, "qr-codes"] as const,
  form: (qr: string | null) => [...leadCaptureKeys.all, "form", qr] as const,
  territories: (parentId: string) => [...leadCaptureKeys.all, "territories", parentId] as const,
};

/** LEAD-013 · The QR codes in the user's scope. */
export function qrCodesQueryOptions() {
  return queryOptions({
    queryKey: leadCaptureKeys.qrCodes(),
    queryFn: ({ signal }) => listQrCodes(signal),
    meta: { dataId: "LEAD-013" },
  });
}

/**
 * LEAD-014 · What the enquiry page needs before the farmer types. States and systems change
 * rarely: ten minutes is fresh enough. An unknown code is a 404, never retried.
 */
export function publicLeadFormQueryOptions(qr: string | null) {
  return queryOptions({
    queryKey: leadCaptureKeys.form(qr),
    queryFn: ({ signal }) => getPublicLeadForm(qr, signal),
    staleTime: 10 * 60_000,
    retry: false,
    meta: { dataId: "LEAD-014" },
  });
}

/** LEAD-014 · A state's districts or a district's talukas. */
export function publicTerritoriesQueryOptions(parentId: string) {
  return queryOptions({
    queryKey: leadCaptureKeys.territories(parentId),
    queryFn: ({ signal }) => listPublicTerritories(parentId, signal),
    staleTime: 10 * 60_000,
    enabled: parentId !== "",
    meta: { dataId: "LEAD-014" },
  });
}
