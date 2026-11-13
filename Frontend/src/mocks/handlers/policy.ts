import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  CONSENT_VERSION_PATTERN,
  POLICY_BOUNDS,
  type PolicyWire,
  type ViewKind,
  type ViewLogPageWire,
  type ViewLogRowWire,
} from "@/features/tracking/api/policy.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_TRACKED } from "@/mocks/data/tracking";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * TRK-006, TRK-007 · The tracking policy and the view log for the mock backend. Versions are
 * kept oldest first; the one in force started last before now. Reads of someone else's route or
 * visits, and of the team map, are logged here by the tracking and visit handlers.
 */

const DEFAULT_CONSENT =
  "While you are on duty, Polysil records your phone's location to plan visits and show your route to your manager. Off duty, nothing is recorded. Location history is kept for 90 days. You can withdraw this consent at any time, which ends your duty.";

/** The seeded first version, as migration 030 writes it. */
function seedPolicy(): PolicyWire {
  return {
    effective_from: "2026-10-01T00:00:00+05:30",
    interval_seconds: 120,
    distance_filter_m: 50,
    working_hours: {
      start: "09:00",
      end: "19:00",
      days: [1, 2, 3, 4, 5, 6],
      timezone: "Asia/Kolkata",
    },
    retention_days: 90,
    visit_photo_required: false,
    consent_version: "v1",
    consent_text: DEFAULT_CONSENT,
  };
}

function versions(): PolicyWire[] {
  if (mockDb.trackingPolicies.length === 0) mockDb.trackingPolicies.push(seedPolicy());
  return mockDb.trackingPolicies;
}

/** The version in force now: the latest that has started. */
export function currentPolicy(now: number = Date.now()): PolicyWire {
  const started = versions().filter((version) => Date.parse(version.effective_from) <= now);
  return started[started.length - 1] ?? seedPolicy();
}

/** The seed's second entry is a look at visits; the others at routes. */
function kindAt(index: number): ViewKind {
  return index === 1 ? "visits" : "route";
}

function seedViewLog(): ViewLogRowWire[] {
  const manager = MOCK_TRACKED.find((person) => person.role === "district_manager");
  const officers = MOCK_TRACKED.filter((person) => person.role === "field_officer");
  if (manager === undefined) return [];
  const viewer = { id: manager.id, full_name: manager.name };
  const at = (hoursAgo: number): string =>
    new Date(Date.now() - hoursAgo * 3_600_000).toISOString();
  const team: ViewLogRowWire = {
    viewer,
    subject: null,
    what: "team",
    viewed_date: null,
    viewed_at: at(1),
  };
  return [
    team,
    ...officers.slice(0, 3).map((officer, index) => ({
      viewer,
      subject: { id: officer.id, full_name: officer.name },
      what: kindAt(index),
      viewed_date: new Date(Date.now() - (index + 1) * 86_400_000).toISOString().slice(0, 10),
      viewed_at: at(3 + index * 5),
    })),
  ];
}

function viewLog(): ViewLogRowWire[] {
  if (mockDb.viewLog === null) mockDb.viewLog = seedViewLog();
  return mockDb.viewLog;
}

/** Record that the signed-in user looked at someone's location, as `_log_view()` does. */
export function logView(what: ViewKind, subjectId: string | null, day: string | null): void {
  const me = mockMeFor(readMockRole()).data;
  if (subjectId === me.id) return;
  const subject =
    subjectId === null ? null : MOCK_TRACKED.find((person) => person.id === subjectId);
  viewLog().unshift({
    viewer: { id: me.id, full_name: me.full_name },
    subject: subject == null ? null : { id: subject.id, full_name: subject.name },
    what,
    viewed_date: day,
    viewed_at: new Date().toISOString(),
  });
}

const HH_MM = /^([01]\d|2[0-3]):[0-5]\d$/;

const policyInSchema = z.object({
  effective_from: z.iso.datetime({ offset: true }),
  interval_seconds: z
    .number()
    .int()
    .min(POLICY_BOUNDS.intervalSeconds.min)
    .max(POLICY_BOUNDS.intervalSeconds.max),
  distance_filter_m: z
    .number()
    .int()
    .min(POLICY_BOUNDS.distanceFilterM.min)
    .max(POLICY_BOUNDS.distanceFilterM.max),
  work_start: z.string().regex(HH_MM, "HH:MM"),
  work_end: z.string().regex(HH_MM, "HH:MM"),
  work_days: z.array(z.number().int().min(1).max(7)).min(1, "At least one day.").max(7),
  retention_days: z
    .number()
    .int()
    .min(POLICY_BOUNDS.retentionDays.min)
    .max(POLICY_BOUNDS.retentionDays.max),
  visit_photo_required: z.boolean(),
  consent_version: z
    .string()
    .regex(CONSENT_VERSION_PATTERN, "Letters, digits, . _ or -, up to 20."),
  consent_text: z.string().min(1).max(POLICY_BOUNDS.consentTextMax),
});

export const policyHandlers = [
  http.get(buildApiUrl("/tracking/policy"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(readMockRole()))
      return errorResponse(403, "forbidden", "Dealers do not track.");
    return HttpResponse.json({ data: currentPolicy() });
  }),

  http.put(buildApiUrl("/tracking/policy"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!can(mockPermissionsFor(readMockRole()), "masters", "edit")) {
      return errorResponse(403, "forbidden", "Needs masters edit.");
    }
    const parsed = policyInSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(
        422,
        "validation_error",
        "Some fields need correcting.",
        Object.fromEntries(
          parsed.error.issues.map((issue) => [issue.path.map(String).join("."), issue.message]),
        ),
      );
    }
    const body = parsed.data;
    if (body.work_end <= body.work_start) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        work_end: "must be after work_start",
      });
    }
    const starts = Date.parse(body.effective_from);
    if (starts < Date.now() - 5 * 60_000) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        effective_from: "must not be in the past",
      });
    }
    if (versions().some((version) => Date.parse(version.effective_from) === starts)) {
      return errorResponse(409, "policy_exists", "A version already starts then.", {
        effective_from: "taken",
      });
    }
    const saved: PolicyWire = {
      effective_from: body.effective_from,
      interval_seconds: body.interval_seconds,
      distance_filter_m: body.distance_filter_m,
      working_hours: {
        start: body.work_start,
        end: body.work_end,
        days: [...body.work_days].sort((left, right) => left - right),
        timezone: "Asia/Kolkata",
      },
      retention_days: body.retention_days,
      visit_photo_required: body.visit_photo_required,
      consent_version: body.consent_version,
      consent_text: body.consent_text,
    };
    mockDb.trackingPolicies.push(saved);
    mockDb.trackingPolicies.sort((left, right) =>
      left.effective_from.localeCompare(right.effective_from),
    );
    return HttpResponse.json({ data: saved });
  }),

  http.get(buildApiUrl("/tracking/view-log"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const permissions = mockPermissionsFor(readMockRole());
    const global =
      can(permissions, "tracking", "view") &&
      permissions.find((entry) => entry.module === "tracking")?.scope === "global";
    const url = new URL(request.url);
    const subject = url.searchParams.get("subject_user_id");
    const rows =
      !global || scenario === "empty"
        ? []
        : viewLog().filter((row) => subject === null || row.subject?.id === subject);
    const limit = Math.min(100, Number(url.searchParams.get("limit") ?? 50) || 50);
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const body: ViewLogPageWire = {
      data: rows.slice(offset, offset + limit),
      meta: {
        limit,
        next_cursor: offset + limit < rows.length ? encodeCursor(offset + limit) : null,
      },
    };
    return HttpResponse.json(body);
  }),
];
