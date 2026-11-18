import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  TARGET_METRICS,
  type AchievementWire,
  type PersonTargetsWire,
  type TargetMetric,
} from "@/features/targets/api/targets.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { readMockRole } from "@/lib/dev/mock-settings";
import { calendarDayOf, todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { mockMeFor } from "@/mocks/data/sessions";
import { MOCK_TEAM } from "@/mocks/data/tasks";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

/**
 * TGT-001, TGT-002 · Targets for the mock backend (`api/services/targets.py`).
 *  - Who: a field officer sees their own row; a manager themselves and the team below them;
 *    Admin everyone who carries targets (Admin carries none, so has no row of their own).
 *  - Achieved: orders approved in the month (the default sale setting) and leads won in it, by
 *    owner. Leads carry no won date here, so a lead counts in the month of its last activity.
 *    Visits belong to a module the mock grants only Admin, so they are null for everyone else.
 *  - Setting: someone below you (Admin: anyone carrying targets), this month to twelve ahead;
 *    a past month only for Admin.
 */

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;
const SALE_TYPES: ReadonlySet<string> = new Set([
  "commercial",
  "industrial",
  "export",
  "subsidised",
]);

interface Person {
  readonly id: string;
  readonly full_name: string;
}

function targetsScope(): string | null {
  return (
    mockPermissionsFor(readMockRole()).find((grant) => grant.module === "targets")?.scope ?? null
  );
}

function canSet(): boolean {
  return (
    mockPermissionsFor(readMockRole())
      .find((grant) => grant.module === "targets")
      ?.actions.includes("create") ?? false
  );
}

function me(): Person {
  const data = mockMeFor(readMockRole()).data;
  return { id: data.id, full_name: data.full_name };
}

/** The people whose targets the caller sees, as the backend lists them. */
function people(scope: string): Person[] {
  if (scope === "global") return [...MOCK_TEAM];
  if (scope === "own") return [me()];
  return [me(), ...MOCK_TEAM];
}

/** Everyone who carries targets: the team, and the signed-in officer or manager. */
function carrier(userId: string): Person | undefined {
  return [me(), ...MOCK_TEAM].find((person) => person.id === userId);
}

function current(userId: string, month: string): Partial<Record<string, string | number>> {
  const values: Partial<Record<string, string | number>> = {};
  for (const entry of mockDb.targets) {
    if (entry.userId === userId && entry.month === month) values[entry.metric] = entry.value;
  }
  return values;
}

function format(metric: TargetMetric, value: number): string | number {
  return metric === "order_value" ? value.toFixed(2) : Math.round(value);
}

function achieved(userId: string, month: string): Record<TargetMetric, number | null> {
  const orders = mockDb.orders.filter(
    (order) =>
      order.owner?.id === userId &&
      SALE_TYPES.has(order.order_type) &&
      order.status !== "draft" &&
      order.status !== "cancelled" &&
      order.approved_at !== null &&
      calendarDayOf(order.approved_at).startsWith(month),
  );
  return {
    order_value: orders.reduce((sum, order) => sum + Number(order.totals.total), 0),
    orders: orders.length,
    leads_won: mockDb.leads.filter(
      (lead) =>
        lead.owner?.id === userId &&
        lead.stage === "won" &&
        calendarDayOf(lead.last_activity_at).startsWith(month),
    ).length,
    visits: readMockRole() === "admin" ? (userId.length * 7) % 23 : null,
  };
}

function pct(achievedValue: number, target: number): string {
  return ((achievedValue / target) * 100).toFixed(1);
}

function achievement(month: string, scope: string, only: string | null): AchievementWire {
  const rows = people(scope)
    .filter((person) => only === null || person.id === only)
    .sort((left, right) => left.full_name.localeCompare(right.full_name));
  const totals: Record<TargetMetric, { target: number; achieved: number | null }> = {
    order_value: { target: 0, achieved: 0 },
    orders: { target: 0, achieved: 0 },
    leads_won: { target: 0, achieved: 0 },
    visits: { target: 0, achieved: 0 },
  };
  const measure = (
    metric: TargetMetric,
    target: number | null,
    got: number | null,
  ): { target: string | number | null; achieved: string | number | null; pct: string | null } => ({
    target: target === null ? null : format(metric, target),
    achieved: got === null ? null : format(metric, got),
    pct: target === null || target === 0 || got === null ? null : pct(got, target),
  });
  const out = rows.map((person) => {
    const set = current(person.id, month);
    const got = achieved(person.id, month);
    const metrics = Object.fromEntries(
      TARGET_METRICS.map((metric) => {
        const raw = set[metric];
        const target = raw === undefined ? null : Number(raw);
        const value = got[metric];
        totals[metric].target += target ?? 0;
        const total = totals[metric];
        total.achieved = value === null || total.achieved === null ? null : total.achieved + value;
        return [metric, measure(metric, target, value)];
      }),
    );
    return {
      user: person,
      metrics: {
        order_value: metrics.order_value ?? measure("order_value", null, null),
        orders: metrics.orders ?? measure("orders", null, null),
        leads_won: metrics.leads_won ?? measure("leads_won", null, null),
        visits: metrics.visits ?? measure("visits", null, null),
      },
    };
  });
  return {
    month,
    as_of: new Date().toISOString(),
    rows: out,
    totals: {
      order_value: measure("order_value", totals.order_value.target, totals.order_value.achieved),
      orders: measure("orders", totals.orders.target, totals.orders.achieved),
      leads_won: measure("leads_won", totals.leads_won.target, totals.leads_won.achieved),
      visits: measure("visits", totals.visits.target, totals.visits.achieved),
    },
    filters: { sale_counted_at: "approval" },
  };
}

function personTargets(person: Person, month: string): PersonTargetsWire {
  const set = current(person.id, month);
  const value = (metric: TargetMetric): string | number | null => {
    const raw = set[metric];
    return raw === undefined ? null : format(metric, Number(raw));
  };
  const orderValue = value("order_value");
  const countOf = (metric: TargetMetric): number | null => {
    const raw = value(metric);
    return raw === null ? null : Number(raw);
  };
  return {
    user: person,
    month,
    targets: {
      order_value: orderValue === null ? null : String(orderValue),
      orders: countOf("orders"),
      leads_won: countOf("leads_won"),
      visits: countOf("visits"),
    },
    history: mockDb.targets
      .filter((entry) => entry.userId === person.id && entry.month === month)
      .reverse()
      .map((entry) => ({
        metric: entry.metric,
        value: entry.value,
        set_by: entry.setBy,
        set_at: entry.setAt,
      })),
  };
}

const putSchema = z.object({
  user_id: z.string().min(1),
  month: z.string(),
  targets: z.record(z.string(), z.union([z.string(), z.number()])),
});

function valueProblem(metric: string, raw: string | number): string | null {
  if (!TARGET_METRICS.some((item) => item === metric)) return "unknown metric";
  const value = Number(raw);
  if (!Number.isFinite(value)) return "a number";
  if (value < 0) return "negative";
  if (metric !== "order_value" && !Number.isInteger(value)) return "a whole number";
  if (metric === "order_value" && Math.round(value * 100) !== value * 100) {
    return "at most two decimal places";
  }
  return null;
}

function monthIndex(month: string): number {
  const [year = 0, index = 1] = month.split("-").map(Number);
  return year * 12 + index - 1;
}

export const targetHandlers = [
  http.get(buildApiUrl("/targets/achievement"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const scope = targetsScope();
    if (scope === null)
      return errorResponse(403, "insufficient_permission", "No targets permission.");
    const params = new URL(request.url).searchParams;
    const month = params.get("month") ?? "";
    if (!MONTH.test(month))
      return errorResponse(422, "validation_error", "Bad month.", { month: "YYYY-MM" });
    return HttpResponse.json({ data: achievement(month, scope, params.get("user_id")) });
  }),

  http.get(buildApiUrl("/targets"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (targetsScope() === null) {
      return errorResponse(403, "insufficient_permission", "No targets permission.");
    }
    const params = new URL(request.url).searchParams;
    const month = params.get("month") ?? "";
    if (!MONTH.test(month))
      return errorResponse(422, "validation_error", "Bad month.", { month: "YYYY-MM" });
    const person = carrier(params.get("user_id") ?? "");
    if (person === undefined) return errorResponse(404, "not_found", "No such person.");
    return HttpResponse.json({ data: personTargets(person, month) });
  }),

  http.put(buildApiUrl("/targets"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (request.headers.get("idempotency-key") === null) {
      return errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.");
    }
    const scope = targetsScope();
    if (scope === null || !canSet()) {
      return errorResponse(403, "insufficient_permission", "No targets.create.");
    }
    const parsed = putSchema.safeParse(await request.json());
    if (!parsed.success || !MONTH.test(parsed.data.month)) {
      return errorResponse(422, "validation_error", "Bad request.", { month: "YYYY-MM" });
    }
    const body = parsed.data;
    const gap = monthIndex(body.month) - monthIndex(todayInIndia().slice(0, 7));
    if (gap > 12) {
      return errorResponse(422, "validation_error", "Too far ahead.", {
        month: "more than 12 months ahead",
      });
    }
    if (gap < 0 && scope !== "global") {
      return errorResponse(422, "month_closed", "Targets for a past month are closed.", {
        month: "past",
      });
    }
    const bad: Record<string, string> = {};
    for (const [metric, value] of Object.entries(body.targets)) {
      const problem = valueProblem(metric, value);
      if (problem !== null) bad[metric] = problem;
    }
    if (Object.keys(body.targets).length === 0) bad.targets = "at least one metric";
    if (Object.keys(bad).length > 0) {
      return errorResponse(422, "validation_error", "Some targets need correcting.", bad);
    }
    const person = carrier(body.user_id);
    if (person === undefined) return errorResponse(404, "not_found", "No such person.");
    if (scope !== "global" && (person.id === me().id || scope === "own")) {
      return errorResponse(403, "not_your_team", "Set targets only for people below you.");
    }
    const setAt = new Date().toISOString();
    for (const [metric, value] of Object.entries(body.targets).sort(([left], [right]) =>
      left.localeCompare(right),
    )) {
      mockDb.targets.push({
        userId: person.id,
        month: body.month,
        metric,
        value: metric === "order_value" ? Number(value).toFixed(2) : Number(value),
        setBy: me(),
        setAt,
      });
    }
    return HttpResponse.json({ data: personTargets(person, body.month) });
  }),
];
