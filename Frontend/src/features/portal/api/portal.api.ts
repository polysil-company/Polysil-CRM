import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import {
  portalComplaintsSchema,
  portalEnquiriesSchema,
  portalMeSchema,
  portalOrdersSchema,
  portalQuotationsSchema,
  portalRatingSchema,
  portalRatingsSchema,
  type PortalComplaint,
  type PortalEnquiry,
  type PortalMe,
  type PortalOrder,
  type PortalQuotation,
  type PortalRating,
  type PortalRatingRequest,
} from "./portal.schemas";

const log = createLogger({ file: "features/portal/api/portal.api.ts", dataId: "FARM-001" });

/** FARM-001 · The farmer's own details and consent. 403 `portal_off`, `not_a_consumer`. */
export function getPortalMe(signal?: AbortSignal): Promise<PortalMe> {
  return apiRequest({
    dataId: "FARM-001",
    logger: log,
    fn: "getPortalMe",
    path: "/portal/me",
    schema: portalMeSchema,
    signal,
  });
}

/** FARM-002 · Record consent now (channel portal), or withdraw it. */
export function patchPortalConsent({
  consentGiven,
  idempotencyKey,
}: {
  readonly consentGiven: boolean;
  readonly idempotencyKey: string;
}): Promise<PortalMe> {
  return apiRequest({
    dataId: "FARM-002",
    logger: log,
    fn: "patchPortalConsent",
    method: "PATCH",
    path: "/portal/me",
    body: { consent_given: consentGiven },
    idempotencyKey,
    schema: portalMeSchema,
  });
}

/** FARM-001 · His enquiries once qualified, newest first. */
export function listPortalEnquiries(signal?: AbortSignal): Promise<PortalEnquiry[]> {
  return apiRequest({
    dataId: "FARM-001",
    logger: log,
    fn: "listPortalEnquiries",
    path: "/portal/enquiries",
    schema: portalEnquiriesSchema,
    signal,
  });
}

/** FARM-001 · His quotations; no total or link on a dealer's. */
export function listPortalQuotations(signal?: AbortSignal): Promise<PortalQuotation[]> {
  return apiRequest({
    dataId: "FARM-001",
    logger: log,
    fn: "listPortalQuotations",
    path: "/portal/quotations",
    schema: portalQuotationsSchema,
    signal,
  });
}

/** FARM-001 · His orders with their dispatches; no total on a dealer's. */
export function listPortalOrders(signal?: AbortSignal): Promise<PortalOrder[]> {
  return apiRequest({
    dataId: "FARM-001",
    logger: log,
    fn: "listPortalOrders",
    path: "/portal/orders",
    schema: portalOrdersSchema,
    signal,
  });
}

/** FARM-001 · His complaints. */
export function listPortalComplaints(signal?: AbortSignal): Promise<PortalComplaint[]> {
  return apiRequest({
    dataId: "FARM-001",
    logger: log,
    fn: "listPortalComplaints",
    path: "/portal/complaints",
    schema: portalComplaintsSchema,
    signal,
  });
}

/** FARM-003 · His ratings, the ones he gave and the ones an officer recorded for him. */
export function listPortalRatings(signal?: AbortSignal): Promise<PortalRating[]> {
  return apiRequest({
    dataId: "FARM-003",
    logger: log,
    fn: "listPortalRatings",
    path: "/portal/ratings",
    schema: portalRatingsSchema,
    signal,
  });
}

/** FARM-003 · Rate an installation or a service. 409 `rating_exists`; 422 `not_rateable`. */
export function createPortalRating({
  body,
  idempotencyKey,
}: {
  readonly body: PortalRatingRequest;
  readonly idempotencyKey: string;
}): Promise<PortalRating> {
  return apiRequest({
    dataId: "FARM-003",
    logger: log,
    fn: "createPortalRating",
    method: "POST",
    path: "/portal/ratings",
    body,
    idempotencyKey,
    schema: portalRatingSchema,
  });
}
