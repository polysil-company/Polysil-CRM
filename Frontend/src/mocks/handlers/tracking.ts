import { http, HttpResponse } from "msw";

import { buildApiUrl } from "@/lib/api/url";
import { can, type ModulePermission } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_TRACKED, mockRoute, mockTeamLatest } from "@/mocks/data/tracking";
import { mockDb } from "@/mocks/db";

import { logView } from "./policy";
import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * TRK-001, TRK-002 · Field tracking for the mock backend (`api/services/tracking.py`).
 * Holders of `tracking.view` see the people in their scope: their own when it is `own`,
 * everyone otherwise. Anyone else gets 403: their role has no tracking.
 */

function scopeOf(permissions: readonly ModulePermission[]): string | null {
  return permissions.find((entry) => entry.module === "tracking")?.scope ?? null;
}

/** The ids the caller may track, or a 403 when their role has no tracking. */
function trackable(): Set<string> | Response {
  const role = readMockRole();
  const permissions = mockPermissionsFor(role);
  if (!can(permissions, "tracking", "view")) {
    return errorResponse(403, "forbidden", "This role has no tracking.");
  }
  const me = mockMeFor(role).data.id;
  return new Set(scopeOf(permissions) === "own" ? [me] : MOCK_TRACKED.map((person) => person.id));
}

export const trackingHandlers = [
  http.get(buildApiUrl("/tracking/team/latest"), async () => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const allowed = trackable();
    if (allowed instanceof Response) return allowed;
    const data =
      scenario === "empty" ? [] : mockTeamLatest().filter((row) => allowed.has(row.user.id));
    logView("team", null, null);
    return HttpResponse.json({ data });
  }),

  http.get(buildApiUrl("/tracking/users/:userId/route"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const allowed = trackable();
    if (allowed instanceof Response) return allowed;
    const person = MOCK_TRACKED.find((item) => item.id === params.userId);
    if (person === undefined || !allowed.has(person.id)) {
      return errorResponse(404, "not_found", "Not in your team.");
    }
    const date = new URL(request.url).searchParams.get("date") ?? "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        date: "A date like 2026-10-18.",
      });
    }
    logView("route", person.id, date);
    const leads = mockDb.leads
      .slice(0, 12)
      .map((lead) => ({ id: lead.id, label: lead.inquiry_no }));
    return HttpResponse.json({ data: mockRoute(person, date, leads) });
  }),
];
