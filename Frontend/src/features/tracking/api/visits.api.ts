import { apiRequest } from "@/lib/api/client";
import { createLogger } from "@/lib/logger";

import type { Visit } from "./tracking.schemas";
import {
  consentRecordedSchema,
  photoLinkSchema,
  trackingConfigSchema,
  visitEnvelopeSchema,
  visitPageSchema,
  visitPhotoSchema,
  type CheckInRequest,
  type CheckOutRequest,
  type TrackingConfig,
  type VisitPage,
  type VisitPhoto,
} from "./visits.schemas";

const log = createLogger({ file: "features/tracking/api/visits.api.ts", dataId: "TRK-003" });

function visitPath(visitId: string, rest = ""): `/${string}` {
  return `/visits/${encodeURIComponent(visitId)}${rest}`;
}

/** TRK-003 · Whether this person tracks, the consent text and version, and the photo rule. */
export function getTrackingConfig(signal?: AbortSignal): Promise<TrackingConfig> {
  return apiRequest({
    dataId: "TRK-003",
    logger: log,
    fn: "getTrackingConfig",
    path: "/me/tracking-config",
    schema: trackingConfigSchema,
    signal,
  });
}

/** TRK-003 · Accept the tracking consent of this version. */
export function acceptTrackingConsent({
  version,
  idempotencyKey,
}: {
  readonly version: string;
  readonly idempotencyKey: string;
}): Promise<null> {
  return apiRequest({
    dataId: "TRK-003",
    logger: log,
    fn: "acceptTrackingConsent",
    method: "POST",
    path: "/tracking/consent",
    body: { version, accepted: true },
    idempotencyKey,
    schema: consentRecordedSchema,
  });
}

/** TRK-003 · Check in. 409 `visit_open` (fields.visit_id), 409 `consent_required`. */
export function checkIn({
  body,
  idempotencyKey,
}: {
  readonly body: CheckInRequest;
  readonly idempotencyKey: string;
}): Promise<Visit> {
  return apiRequest({
    dataId: "TRK-003",
    logger: log,
    fn: "checkIn",
    method: "POST",
    path: "/visits",
    body,
    idempotencyKey,
    schema: visitEnvelopeSchema,
  });
}

/** TRK-004 · Check out of an open visit. 409 `visit_closed`, `photo_required`. */
export function checkOut({
  visitId,
  body,
  idempotencyKey,
}: {
  readonly visitId: string;
  readonly body: CheckOutRequest;
  readonly idempotencyKey: string;
}): Promise<Visit> {
  return apiRequest({
    dataId: "TRK-004",
    logger: log,
    fn: "checkOut",
    method: "POST",
    path: visitPath(visitId, "/check-out"),
    body,
    idempotencyKey,
    schema: visitEnvelopeSchema,
  });
}

/** TRK-004 · One photo, multipart. 409 `photo_limit`, `photo_window_closed`; 413 over 10 MB. */
export function uploadVisitPhoto({
  visitId,
  file,
  idempotencyKey,
}: {
  readonly visitId: string;
  /** A picked `File`, or any named Blob. */
  readonly file: Blob & { readonly name: string };
  readonly idempotencyKey: string;
}): Promise<VisitPhoto> {
  const body = new FormData();
  body.append("file", file, file.name);
  return apiRequest({
    dataId: "TRK-004",
    logger: log,
    fn: "uploadVisitPhoto",
    method: "POST",
    path: visitPath(visitId, "/photos"),
    body,
    idempotencyKey,
    // Uploads over a field connection take longer than a JSON call.
    timeoutMs: 90_000,
    schema: visitPhotoSchema,
  });
}

/** TRK-004 · A ten-minute link to a visit's photo. */
export function getVisitPhotoLink(
  visitId: string,
  photoId: string,
  signal?: AbortSignal,
): Promise<{ url: string; expiresAt: string }> {
  return apiRequest({
    dataId: "TRK-004",
    logger: log,
    fn: "getVisitPhotoLink",
    path: visitPath(visitId, `/photos/${encodeURIComponent(photoId)}`),
    schema: photoLinkSchema,
    signal,
  });
}

/** TRK-005 · My visits of one Indian day, newest first. */
export function listMyVisits(
  { date, cursor }: { readonly date: string; readonly cursor: string | null },
  signal?: AbortSignal,
): Promise<VisitPage> {
  return apiRequest({
    dataId: "TRK-005",
    logger: log,
    fn: "listMyVisits",
    path: "/visits",
    query: { user_id: "me", date, limit: 50, cursor },
    schema: visitPageSchema,
    signal,
  });
}

/** TRK-005 · One visit. */
export function getVisit(visitId: string, signal?: AbortSignal): Promise<Visit> {
  return apiRequest({
    dataId: "TRK-005",
    logger: log,
    fn: "getVisit",
    path: visitPath(visitId),
    schema: visitEnvelopeSchema,
    signal,
  });
}
