import { keepPreviousData, queryOptions } from "@tanstack/react-query";

import { getDealerApplication, listDealerApplications } from "./dealer-applications.api";
import type { DealerApplicationListParams } from "./dealer-applications.schemas";
import { checkApplicantGstin, getApplicantView } from "./dealer-apply.api";

/** A write to one application moves it in the list too: mutations invalidate `all`. */
export const dealerApplicationKeys = {
  all: ["dealer-applications"] as const,
  list: (params: DealerApplicationListParams) =>
    [...dealerApplicationKeys.all, "list", params] as const,
  detail: (applicationId: string) =>
    [...dealerApplicationKeys.all, "detail", applicationId] as const,
};

/** CHNL-007 · The applications in scope (at most 200), filtered. */
export function dealerApplicationListQueryOptions(params: DealerApplicationListParams) {
  return queryOptions({
    queryKey: dealerApplicationKeys.list(params),
    queryFn: ({ signal }) => listDealerApplications(params, signal),
    placeholderData: keepPreviousData,
    meta: { dataId: "CHNL-007" },
  });
}

/** CHNL-007 · One application. */
export function dealerApplicationQueryOptions(applicationId: string) {
  return queryOptions({
    queryKey: dealerApplicationKeys.detail(applicationId),
    queryFn: ({ signal }) => getDealerApplication(applicationId, signal),
    meta: { dataId: "CHNL-007" },
  });
}

/** CHNL-008 · What the applicant's link shows; every field once `session` is set. */
export function applicantViewQueryOptions(token: string, session: string | null) {
  return queryOptions({
    queryKey: [...dealerApplicationKeys.all, "applicant", token, session] as const,
    queryFn: ({ signal }) => getApplicantView({ token, session }, signal),
    retry: false,
    meta: { dataId: "CHNL-008" },
  });
}

/** CHNL-008 · "Check GSTIN" on the applicant's page: the GSTIN read from itself. */
export function applicantGstinQueryOptions(token: string, session: string | null, gstin: string) {
  return queryOptions({
    queryKey: [...dealerApplicationKeys.all, "applicant-gstin", token, session, gstin] as const,
    queryFn: ({ signal }) => checkApplicantGstin({ token, session }, gstin, signal),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
    meta: { dataId: "CHNL-008" },
  });
}
