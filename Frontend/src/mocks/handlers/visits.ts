import { http, HttpResponse } from "msw";
import { z } from "zod";

import { type VisitWire, VISIT_OUTCOMES } from "@/features/tracking/api/tracking.schemas";
import {
  VISIT_PHOTO_MAX,
  VISIT_PHOTO_MAX_BYTES,
  VISIT_PHOTO_TYPES,
  type TrackingConfigWire,
  type VisitPageWire,
  type VisitPhotoWire,
} from "@/features/tracking/api/visits.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { calendarDayOf } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockUuid } from "@/mocks/data/reference";
import { mockMeFor } from "@/mocks/data/sessions";
import { TRACKING_SPACE } from "@/mocks/data/tracking";
import { mockDb } from "@/mocks/db";

import { currentPolicy, logView } from "./policy";
import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * TRK-003 … TRK-005 · Visits for the mock backend (`api/services/tracking.py`). Anyone who
 * tracks (`tracking.create`) checks in, once they accepted this version of the consent. One open
 * visit at a time; up to three photos within 24 hours of check-in.
 */

const PHOTO_WINDOW_MS = 24 * 60 * 60 * 1000;

/** The files themselves, so a photo opens as it was taken; lost on a reload, like the mock. */
const photoFiles = new Map<string, Blob>();

function linkTo(photoId: string): string {
  const file = photoFiles.get(photoId);
  if (file === undefined) return "/icon.svg";
  try {
    return URL.createObjectURL(file);
  } catch {
    return "/icon.svg";
  }
}

function me(): { id: string; full_name: string; tracks: boolean } {
  const role = readMockRole();
  const user = mockMeFor(role).data;
  return {
    id: user.id,
    full_name: user.full_name,
    tracks: can(mockPermissionsFor(role), "tracking", "create"),
  };
}

function noTracking(): Response {
  return errorResponse(403, "forbidden", "This role does not track.");
}

/** The visit, if it is the caller's own. */
function ownVisit(visitId: unknown, userId: string): VisitWire | undefined {
  return mockDb.visits.find((visit) => visit.id === visitId && visit.user.id === userId);
}

const positionFields = {
  at: z.iso.datetime({ offset: true }),
  sent_at: z.iso.datetime({ offset: true }).nullish(),
  lat: z.number().min(-90).max(90),
  lng: z.number().min(-180).max(180),
  accuracy_m: z.number().nonnegative().nullish(),
};

const checkInSchema = z.object({
  id: z.string().min(1),
  lead_id: z.string().min(1).nullish(),
  partner_id: z.string().min(1).nullish(),
  task_id: z.string().min(1).nullish(),
  place_name: z.string().trim().max(200).nullish(),
  ...positionFields,
});

const checkOutSchema = z.object({
  ...positionFields,
  outcome: z.enum(VISIT_OUTCOMES),
  note: z.string().max(2000).nullish(),
});

function fieldErrors(issues: readonly z.core.$ZodIssue[]): Record<string, string> {
  return Object.fromEntries(
    issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
  );
}

export const visitHandlers = [
  http.get(buildApiUrl("/me/tracking-config"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const caller = me();
    const policy = currentPolicy();
    const config: TrackingConfigWire = {
      tracking_allowed: caller.tracks,
      consent: {
        required_version: policy.consent_version,
        accepted_version: mockDb.trackingConsent.get(caller.id) ?? null,
        text: policy.consent_text,
      },
      interval_seconds: 120,
      distance_filter_m: 50,
      working_hours: {
        start: "09:00",
        end: "19:00",
        days: [1, 2, 3, 4, 5, 6],
        timezone: "Asia/Kolkata",
      },
      max_batch_points: 500,
      visit_photo_required: policy.visit_photo_required,
      on_duty: null,
    };
    return HttpResponse.json({ data: config });
  }),

  http.post(buildApiUrl("/tracking/consent"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const caller = me();
    if (!caller.tracks) return noTracking();
    const parsed = z
      .object({ version: z.string().min(1), accepted: z.boolean() })
      .safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldErrors(parsed.error.issues),
      );
    }
    if (parsed.data.accepted) {
      mockDb.trackingConsent.set(caller.id, parsed.data.version);
    } else {
      mockDb.trackingConsent.delete(caller.id);
    }
    return HttpResponse.json(
      {
        data: {
          version: parsed.data.version,
          accepted: parsed.data.accepted,
          at: new Date().toISOString(),
        },
      },
      { status: 201 },
    );
  }),

  http.get(buildApiUrl("/visits"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const caller = me();
    if (!can(mockPermissionsFor(readMockRole()), "tracking", "view")) return noTracking();
    const url = new URL(request.url);
    const userId = url.searchParams.get("user_id");
    const date = url.searchParams.get("date");
    const who = userId === null || userId === "me" ? caller.id : userId;
    logView("visits", who, date);
    const matches =
      scenario === "empty"
        ? []
        : mockDb.visits
            .filter((visit) => visit.user.id === who)
            .filter((visit) => date === null || calendarDayOf(visit.checkin_at) === date);
    const limit = Math.min(100, Number(url.searchParams.get("limit") ?? 50) || 50);
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const body: VisitPageWire = {
      data: matches.slice(offset, offset + limit),
      meta: {
        limit,
        next_cursor: offset + limit < matches.length ? encodeCursor(offset + limit) : null,
      },
    };
    return HttpResponse.json(body);
  }),

  http.get(buildApiUrl("/visits/:visitId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const visit = ownVisit(params.visitId, me().id);
    if (visit === undefined)
      return errorResponse(404, "not_found", "Not yours, or not in your team.");
    return HttpResponse.json({ data: visit });
  }),

  http.post(buildApiUrl("/visits"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const caller = me();
    if (!caller.tracks) return noTracking();
    const parsed = checkInSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldErrors(parsed.error.issues),
      );
    }
    const body = parsed.data;
    const replay = mockDb.visits.find((visit) => visit.id === body.id);
    if (replay !== undefined) return HttpResponse.json({ data: replay });
    if (mockDb.trackingConsent.get(caller.id) !== currentPolicy().consent_version) {
      return errorResponse(409, "consent_required", "Accept the tracking consent first.");
    }
    const place = body.place_name?.trim() || null;
    if (body.lead_id != null && body.partner_id != null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        partner_id: "A lead or a dealer, not both.",
      });
    }
    if (body.lead_id == null && body.partner_id == null && place === null) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        place_name: "Name the place when it is not a lead or a dealer.",
      });
    }
    const open = mockDb.visits.find(
      (visit) => visit.user.id === caller.id && visit.checkout_at === null,
    );
    if (open !== undefined) {
      return errorResponse(409, "visit_open", "Check out of your open visit first.", {
        visit_id: open.id,
      });
    }
    const lead =
      body.lead_id == null ? null : mockDb.leads.find((item) => item.id === body.lead_id);
    const partner =
      body.partner_id == null ? null : mockDb.partners.find((item) => item.id === body.partner_id);
    if (lead === undefined || partner === undefined) {
      return errorResponse(404, "not_found", "Not a lead or dealer you can see.");
    }
    const visit: VisitWire = {
      id: body.id,
      user: { id: caller.id, full_name: caller.full_name },
      lead: lead === null ? null : { id: lead.id, label: lead.inquiry_no },
      partner: partner === null ? null : { id: partner.id, label: partner.name },
      task_id: body.task_id ?? null,
      place_name: lead === null && partner === null ? place : null,
      checkin_at: body.at,
      checkin: { lat: body.lat, lng: body.lng, accuracy_m: body.accuracy_m ?? null },
      checkout_at: null,
      checkout: null,
      duration_minutes: null,
      outcome: null,
      note: null,
      auto_closed: false,
      photo_count: 0,
    };
    mockDb.visits.unshift(visit);
    return HttpResponse.json({ data: visit }, { status: 201 });
  }),

  http.post(buildApiUrl("/visits/:visitId/check-out"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const caller = me();
    if (!caller.tracks) return noTracking();
    const visit = ownVisit(params.visitId, caller.id);
    if (visit === undefined) return errorResponse(404, "not_found", "Not yours.");
    if (visit.checkout_at !== null) {
      return errorResponse(409, "visit_closed", "This visit is already closed.");
    }
    if (currentPolicy().visit_photo_required && visit.photo_count === 0) {
      return errorResponse(409, "photo_required", "Add a photo of the visit first.");
    }
    const parsed = checkOutSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        fieldErrors(parsed.error.issues),
      );
    }
    const body = parsed.data;
    Object.assign(visit, {
      checkout_at: body.at,
      checkout: { lat: body.lat, lng: body.lng, accuracy_m: body.accuracy_m ?? null },
      duration_minutes: Math.max(
        0,
        Math.round((Date.parse(body.at) - Date.parse(visit.checkin_at)) / 60_000),
      ),
      outcome: body.outcome,
      note: body.note?.trim() || null,
    });
    return HttpResponse.json({ data: visit });
  }),

  http.post(buildApiUrl("/visits/:visitId/photos"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const caller = me();
    if (!caller.tracks) return noTracking();
    const visit = ownVisit(params.visitId, caller.id);
    if (visit === undefined) return errorResponse(404, "not_found", "Not yours.");
    const file = (await request.formData()).get("file");
    // A shape check, not `instanceof Blob`: the parsed part may come from another realm.
    if (file === null || typeof file === "string") {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        file: "Choose a photo.",
      });
    }
    if (file.size > VISIT_PHOTO_MAX_BYTES) return errorResponse(413, "too_large", "Over 10 MB.");
    if (!VISIT_PHOTO_TYPES.some((type) => type === file.type)) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        file: "A JPEG, PNG, WebP or HEIC photo.",
      });
    }
    const photos = mockDb.visitPhotos.get(visit.id) ?? [];
    if (photos.length >= VISIT_PHOTO_MAX) {
      return errorResponse(409, "photo_limit", "A visit takes up to 3 photos.");
    }
    if (Date.now() - Date.parse(visit.checkin_at) > PHOTO_WINDOW_MS) {
      return errorResponse(
        409,
        "photo_window_closed",
        "Photos are taken until 24 hours after check-in.",
      );
    }
    const photo: VisitPhotoWire = {
      id: mockUuid(TRACKING_SPACE, 5000 + mockDb.visitPhotos.size * 10 + photos.length),
      content_type: file.type,
      size_bytes: file.size,
      uploaded_at: new Date().toISOString(),
    };
    photoFiles.set(photo.id, file);
    mockDb.visitPhotos.set(visit.id, [...photos, photo]);
    visit.photo_count = photos.length + 1;
    return HttpResponse.json({ data: photo }, { status: 201 });
  }),

  http.get(buildApiUrl("/visits/:visitId/photos/:photoId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const visit = ownVisit(params.visitId, me().id);
    const photo =
      visit === undefined
        ? undefined
        : mockDb.visitPhotos.get(visit.id)?.find((item) => item.id === params.photoId);
    if (photo === undefined) return errorResponse(404, "not_found", "No such photo.");
    return HttpResponse.json({
      data: {
        url: linkTo(photo.id),
        expires_at: new Date(Date.now() + 10 * 60_000).toISOString(),
      },
    });
  }),
];
