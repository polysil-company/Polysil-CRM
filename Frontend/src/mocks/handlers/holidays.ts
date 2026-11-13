import { http, HttpResponse } from "msw";
import { z } from "zod";

import { HOLIDAY_NAME_MAX_LENGTH } from "@/features/masters/api/holidays.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * MSTR-019 · Holidays (`complaint-holidays-escalation.md`): anyone signed in reads a year;
 * masters.edit adds one from tomorrow on (not a Sunday) and removes one still ahead.
 */

function mayEdit(): boolean {
  return can(mockPermissionsFor(readMockRole()), "masters", "edit");
}

const addSchema = z.object({
  day: z.iso.date("A date."),
  name: z.string().trim().min(1, "Name the holiday.").max(HOLIDAY_NAME_MAX_LENGTH),
});

function isSunday(day: string): boolean {
  return new Date(`${day}T00:00:00Z`).getUTCDay() === 0;
}

export const holidayHandlers = [
  http.get(buildApiUrl("/holidays"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const year = new URL(request.url).searchParams.get("year");
    return HttpResponse.json({
      data: mockDb.holidays
        .filter((holiday) => year === null || holiday.day.startsWith(`${year}-`))
        .sort((left, right) => left.day.localeCompare(right.day)),
    });
  }),

  http.post(buildApiUrl("/holidays"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit()) return errorResponse(403, "forbidden", "Needs masters.edit.");
    const parsed = addSchema.safeParse(await request.json());
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
    const { day, name } = parsed.data;
    if (day <= todayInIndia()) {
      return errorResponse(422, "holiday_in_past", "A holiday is added for tomorrow or later.");
    }
    if (isSunday(day)) {
      return errorResponse(422, "holiday_sunday", "Sundays already don't count.");
    }
    if (mockDb.holidays.some((holiday) => holiday.day === day)) {
      return errorResponse(409, "holiday_exists", "That day is already a holiday.");
    }
    const holiday = { day, name };
    mockDb.holidays.push(holiday);
    return HttpResponse.json({ data: holiday }, { status: 201 });
  }),

  http.delete(buildApiUrl("/holidays/:day"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit()) return errorResponse(403, "forbidden", "Needs masters.edit.");
    const day = String(params.day);
    const holiday = mockDb.holidays.find((item) => item.day === day);
    if (holiday === undefined) return errorResponse(404, "not_found", "No such holiday.");
    if (day <= todayInIndia()) {
      return errorResponse(409, "holiday_in_past", "Complaints were counted with it; it stays.");
    }
    mockDb.holidays = mockDb.holidays.filter((item) => item.day !== day);
    return new HttpResponse(null, { status: 204 });
  }),
];
