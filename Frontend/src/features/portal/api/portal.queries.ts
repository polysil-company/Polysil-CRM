import { queryOptions } from "@tanstack/react-query";

import {
  getPortalMe,
  listPortalComplaints,
  listPortalEnquiries,
  listPortalOrders,
  listPortalQuotations,
  listPortalRatings,
} from "./portal.api";

/** Query keys for the farmers' portal. `portalKeys.all` covers everything the farmer reads. */
export const portalKeys = {
  all: ["portal"] as const,
  me: () => [...portalKeys.all, "me"] as const,
  enquiries: () => [...portalKeys.all, "enquiries"] as const,
  quotations: () => [...portalKeys.all, "quotations"] as const,
  orders: () => [...portalKeys.all, "orders"] as const,
  complaints: () => [...portalKeys.all, "complaints"] as const,
  ratings: () => [...portalKeys.all, "ratings"] as const,
};

export function portalMeQueryOptions() {
  return queryOptions({
    queryKey: portalKeys.me(),
    queryFn: ({ signal }) => getPortalMe(signal),
    meta: { dataId: "FARM-001" },
  });
}

export function portalEnquiriesQueryOptions() {
  return queryOptions({
    queryKey: portalKeys.enquiries(),
    queryFn: ({ signal }) => listPortalEnquiries(signal),
    meta: { dataId: "FARM-001" },
  });
}

export function portalQuotationsQueryOptions() {
  return queryOptions({
    queryKey: portalKeys.quotations(),
    queryFn: ({ signal }) => listPortalQuotations(signal),
    meta: { dataId: "FARM-001" },
  });
}

export function portalOrdersQueryOptions() {
  return queryOptions({
    queryKey: portalKeys.orders(),
    queryFn: ({ signal }) => listPortalOrders(signal),
    meta: { dataId: "FARM-001" },
  });
}

export function portalComplaintsQueryOptions() {
  return queryOptions({
    queryKey: portalKeys.complaints(),
    queryFn: ({ signal }) => listPortalComplaints(signal),
    meta: { dataId: "FARM-001" },
  });
}

export function portalRatingsQueryOptions() {
  return queryOptions({
    queryKey: portalKeys.ratings(),
    queryFn: ({ signal }) => listPortalRatings(signal),
    meta: { dataId: "FARM-003" },
  });
}
