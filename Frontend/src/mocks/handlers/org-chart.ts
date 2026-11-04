import { http, HttpResponse } from "msw";

import type { OrgChartWire } from "@/features/org-chart/api/org-chart.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_ROLES, type MockUserRecord } from "@/mocks/data/users";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * ADMN-008 · The org chart for the mock backend, as `reporting_lines()` (migration 083) works
 * it out: a person reports to the nearest higher **line** role (not a functional one) in their
 * own office, or the offices above it. Nothing is stored, so any change of office or role shows
 * at once. Registered before `/users/:userId`, so "org-chart" isn't read as an id.
 */

interface Placed {
  readonly user: MockUserRecord;
  readonly level: number;
  readonly officeId: string;
}

function lineLevel(code: string | undefined): number | null {
  const role = MOCK_ROLES.find((item) => item.code === code);
  if (role === undefined || role.is_portal || role.is_functional) return null;
  return role.level;
}

/** Active staff on a line role with an office: the people a chart can place. */
function placed(): Placed[] {
  return mockDb.users.flatMap((user) => {
    const level = lineLevel(user.role?.code);
    if (
      user.deleted_at !== null ||
      !user.is_active ||
      user.user_type !== "staff" ||
      level === null ||
      user.org_unit === null
    ) {
      return [];
    }
    return [{ user, level, officeId: user.org_unit.id }];
  });
}

/** An office, then the offices above it, nearest first. */
function officeChain(officeId: string): string[] {
  const chain: string[] = [];
  let current: string | null = officeId;
  while (current !== null && !chain.includes(current)) {
    chain.push(current);
    const office = mockDb.offices.find((item) => item.id === current);
    current = office?.parent?.id ?? null;
  }
  return chain;
}

/** Each person's managers: the lowest higher level in the nearest office that has one. */
function managersOf(person: Placed, everyone: readonly Placed[]): Placed[] {
  for (const officeId of officeChain(person.officeId)) {
    const above = everyone.filter(
      (other) => other.officeId === officeId && other.level > person.level,
    );
    if (above.length === 0) continue;
    const nearest = Math.min(...above.map((other) => other.level));
    return above
      .filter((other) => other.level === nearest)
      .sort((a, b) => a.user.full_name.localeCompare(b.user.full_name));
  }
  return [];
}

function personWire(person: Placed): OrgChartWire["managers"][number][number] {
  return {
    id: person.user.id,
    full_name: person.user.full_name,
    role: { code: person.user.role?.code ?? "", name: person.user.role?.name ?? "" },
    level: person.level,
    org_unit: { id: person.officeId, name: person.user.org_unit?.name ?? "" },
  };
}

function chart(subjectId: string | null): OrgChartWire | null {
  const everyone = placed();
  const managers = new Map(
    everyone.map((person) => [person.user.id, managersOf(person, everyone)]),
  );
  const below = (id: string): Placed[] => {
    const found = new Map<string, Placed>();
    const visit = (managerId: string): void => {
      for (const person of everyone) {
        if (found.has(person.user.id)) continue;
        if ((managers.get(person.user.id) ?? []).some((m) => m.user.id === managerId)) {
          found.set(person.user.id, person);
          visit(person.user.id);
        }
      }
    };
    visit(id);
    return [...found.values()];
  };
  const subject =
    subjectId === null ? null : everyone.find((person) => person.user.id === subjectId);
  if (subject === undefined) return null;
  const people = subject === null ? everyone : below(subject.user.id);
  const chain: Placed[][] = [];
  let step = subject === null ? [] : (managers.get(subject.user.id) ?? []);
  while (step.length > 0 && chain.length < 10) {
    chain.push(step);
    const first = step[0];
    step = first === undefined ? [] : (managers.get(first.user.id) ?? []);
  }
  const shown = new Set([
    ...(subject === null ? [] : [subject.user.id]),
    ...chain.flat().map((person) => person.user.id),
    ...people.map((person) => person.user.id),
  ]);
  const coManagers = new Map<string, Placed>();
  for (const person of people) {
    for (const manager of managers.get(person.user.id) ?? []) {
      if (!shown.has(manager.user.id)) coManagers.set(manager.user.id, manager);
    }
  }
  const sorted = [...people].sort(
    (a, b) => b.level - a.level || a.user.full_name.localeCompare(b.user.full_name),
  );
  const byRole = new Map<
    string,
    { role: { code: string; name: string }; count: number; level: number }
  >();
  for (const person of sorted) {
    const code = person.user.role?.code ?? "";
    const entry = byRole.get(code) ?? {
      role: { code, name: person.user.role?.name ?? code },
      count: 0,
      level: person.level,
    };
    entry.count += 1;
    byRole.set(code, entry);
  }
  return {
    subject: subject === null ? null : personWire(subject),
    managers: chain.map((items) => items.map(personWire)),
    people: sorted.map((person) => ({
      ...personWire(person),
      manager_ids: (managers.get(person.user.id) ?? []).map((manager) => manager.user.id),
      direct_reports: everyone.filter((other) =>
        (managers.get(other.user.id) ?? []).some((m) => m.user.id === person.user.id),
      ).length,
      team_size: below(person.user.id).length,
    })),
    co_managers: [...coManagers.values()].map(personWire),
    totals: {
      people: sorted.length,
      by_role: [...byRole.values()]
        .sort((a, b) => b.level - a.level)
        .map(({ role, count }) => ({ role, count })),
    },
    unplaced: [],
  };
}

/** The mock's role as the backend's role code. */
const BACKEND_ROLE: Readonly<Record<string, string>> = {
  admin: "admin_sales",
  employee: "field_officer",
  qa_manager: "qc_manager",
};

/**
 * Who "me" is: every mock role shares one session id, so the chart takes the first active
 * person seeded with the signed-in role (a field officer's own line, a district manager's
 * team), and the session's id when there is none.
 */
function meFor(role: string): string {
  const code = BACKEND_ROLE[role] ?? role;
  const seeded = mockDb.users.find(
    (user) => user.deleted_at === null && user.is_active && user.role?.code === code,
  );
  return seeded?.id ?? mockMeFor(role).data.id;
}

export const orgChartHandlers = [
  http.get(buildApiUrl("/users/org-chart"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const role = readMockRole();
    if (isPartnerRole(role)) {
      return errorResponse(403, "insufficient_permission", "The org chart is for staff.");
    }
    const url = new URL(request.url);
    const view = url.searchParams.get("view");
    const userId = url.searchParams.get("user_id");
    if (view !== null && view !== "company")
      return errorResponse(422, "validation_error", "Check the fields.", {
        view: "company or nothing",
      });
    if (view !== null && userId !== null) {
      return errorResponse(422, "validation_error", "Check the fields.", {
        view: "not with user_id",
      });
    }
    const global = can(mockPermissionsFor(role), "users", "view");
    if (view === "company") {
      if (!global) {
        return errorResponse(
          403,
          "insufficient_permission",
          "The whole company is for users.view.",
        );
      }
      const company = chart(null);
      return HttpResponse.json({ data: company });
    }
    const me = meFor(role);
    const subjectId = userId ?? me;
    const picture = chart(subjectId);
    if (picture === null) {
      return errorResponse(404, "not_found", "No reporting line to show.");
    }
    // Someone else's picture: only someone below me, unless I see every user.
    if (subjectId !== me && !global) {
      const mine = chart(me);
      if (mine === null || !mine.people.some((person) => person.id === subjectId)) {
        return errorResponse(404, "not_found", "No reporting line to show.");
      }
    }
    return HttpResponse.json({ data: picture });
  }),
];
