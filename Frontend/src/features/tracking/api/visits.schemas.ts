import { z } from "zod";

import { cursorPageSchema, type CursorPage, type PageMetaWire } from "@/lib/api/pagination";

import {
  visitOf,
  visitWireSchema,
  type Visit,
  type VisitOutcome,
  type VisitWire,
} from "./tracking.schemas";

/**
 * TRK-003 … TRK-005 · Visits on the web (`field-tracking-contract.md` §3 Visits). Check-in and
 * check-out carry the browser's fix; the server corrects a clock that is off when `sent_at`
 * comes with it.
 */

const isoDateTime = z.iso.datetime({ offset: true });

const trackingConfigWireSchema = z.object({
  /** False: this role does not track. */
  tracking_allowed: z.boolean(),
  consent: z.object({
    required_version: z.string(),
    accepted_version: z.string().nullable(),
    text: z.string(),
  }),
  interval_seconds: z.number().int().positive(),
  distance_filter_m: z.number().int().nonnegative(),
  working_hours: z.object({
    start: z.string(),
    end: z.string(),
    days: z.array(z.number().int().min(1).max(7)),
    timezone: z.string().optional(),
  }),
  max_batch_points: z.number().int().positive(),
  /** True: check-out needs at least one photo. */
  visit_photo_required: z.boolean(),
  on_duty: z.object({ id: z.string().min(1), started_at: isoDateTime }).nullable(),
});
export type TrackingConfigWire = z.input<typeof trackingConfigWireSchema>;

export const trackingConfigSchema = z
  .object({ data: trackingConfigWireSchema })
  .transform(({ data }) => ({
    trackingAllowed: data.tracking_allowed,
    consent: {
      requiredVersion: data.consent.required_version,
      acceptedVersion: data.consent.accepted_version,
      text: data.consent.text,
      /** The current version is accepted: nothing to ask. */
      accepted: data.consent.accepted_version === data.consent.required_version,
    },
    visitPhotoRequired: data.visit_photo_required,
  }));
export type TrackingConfig = z.output<typeof trackingConfigSchema>;

/** `POST /tracking/consent` answers what was recorded; the screens need only that it worked. */
export const consentRecordedSchema = z.object({ data: z.unknown() }).transform(() => null);

export const visitEnvelopeSchema = z
  .object({ data: visitWireSchema })
  .transform(({ data }) => visitOf(data));

export const visitPageSchema = cursorPageSchema(visitWireSchema.transform(visitOf));
export type VisitPage = CursorPage<Visit>;
export type VisitPageWire = { data: VisitWire[]; meta: PageMetaWire };

const visitPhotoWireSchema = z.object({
  id: z.string().min(1),
  content_type: z.string(),
  size_bytes: z.number().int().nonnegative(),
  uploaded_at: isoDateTime,
});
export type VisitPhotoWire = z.input<typeof visitPhotoWireSchema>;

export const visitPhotoSchema = z.object({ data: visitPhotoWireSchema }).transform(({ data }) => ({
  id: data.id,
  contentType: data.content_type,
  sizeBytes: data.size_bytes,
  uploadedAt: data.uploaded_at,
}));
export type VisitPhoto = z.output<typeof visitPhotoSchema>;

export const photoLinkSchema = z
  .object({ data: z.object({ url: z.string().min(1), expires_at: isoDateTime }) })
  .transform(({ data }) => ({ url: data.url, expiresAt: data.expires_at }));

/** A fix from the browser: where, and how sure. */
export interface Fix {
  readonly lat: number;
  readonly lng: number;
  readonly accuracyM: number | null;
  /** When the fix was taken. */
  readonly at: string;
}

export interface CheckInRequest {
  readonly id: string;
  readonly lead_id: string | null;
  readonly partner_id: string | null;
  readonly place_name: string | null;
  readonly at: string;
  readonly sent_at: string;
  readonly lat: number;
  readonly lng: number;
  readonly accuracy_m: number | null;
}

export interface CheckOutRequest {
  readonly at: string;
  readonly sent_at: string;
  readonly lat: number;
  readonly lng: number;
  readonly accuracy_m: number | null;
  readonly outcome: VisitOutcome;
  readonly note: string | null;
}

/** The contract: up to 3 photos a visit, 10 MB each, until 24 hours after check-in. */
export const VISIT_PHOTO_MAX = 3;
export const VISIT_PHOTO_MAX_BYTES = 10 * 1024 * 1024;
export const VISIT_PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp", "image/heic"] as const;
/** Above this the fix is too rough to say where the visit was: warn before checking in. */
export const FIX_WARN_METRES = 100;
