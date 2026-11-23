import { http, HttpResponse } from "msw";
import { z } from "zod";

import {
  BENEFIT_KINDS,
  CONDITION_METRICS,
  KINDS_FOR_TYPE,
  PARTNER_TYPES,
  SCHEME_PERIODS,
  SCHEME_TYPES,
  TARGET_TYPES,
  type SchemeWire,
  type StandingWire,
} from "@/features/schemes/api/schemes.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { isPartnerRole } from "@/lib/auth/roles";
import { readMockRole } from "@/lib/dev/mock-settings";
import { shiftCalendarDay, todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_PRODUCT_CATEGORIES } from "@/mocks/data/products";
import { mockSchemeId } from "@/mocks/data/schemes";
import { mockMeFor } from "@/mocks/data/sessions";
import { findMockTerritory, MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * SCHM-001 … SCHM-004 · Schemes for the mock backend (`api/services/schemes.py`).
 *  - Staff see every scheme; a partner user only the running ones aimed at it (its partner,
 *    its type, or a territory: every mock partner is in Gujarat), never partner targets.
 *  - Create and change follow the backend's rules, including `scheme_in_use` once a scheme has
 *    given a benefit and `code_taken`.
 *  - A period scheme's standing is drawn from the partner's id; the mock keeps no deliveries.
 *  - Also GET /territories/{id}, which names a scheme's territory targets.
 */

const PAGE = 50;

function role(): ReturnType<typeof readMockRole> {
  return readMockRole();
}

function may(action: "view" | "create" | "edit"): boolean {
  return can(mockPermissionsFor(role()), "schemes", action);
}

/** The partner the signed-in partner user belongs to, with its type. */
function myPartner(): { id: string; type: string } | null {
  const current = role();
  if (!isPartnerRole(current)) return null;
  const partner = mockMeFor(current).data.partner;
  return partner == null ? null : { id: partner.id, type: current };
}

function aimedAt(scheme: SchemeWire, partner: { id: string; type: string }): boolean {
  // Products don't decide who sees a scheme; each partner kind present must match. Every mock
  // partner is in Gujarat, so a territory target always does.
  const match = (kind: "partner_type" | "partner"): boolean => {
    const ids = scheme.targets.filter((target) => target.type === kind).map((target) => target.id);
    return ids.length === 0 || ids.includes(kind === "partner" ? partner.id : partner.type);
  };
  return match("partner_type") && match("partner");
}

/** BE-027 · A target's name, as the backend sends it: the record's, or the type itself. */
function targetName(target: SchemeWire["targets"][number]): string | null {
  switch (target.type) {
    case "partner_type":
      return target.id;
    case "territory":
      return findMockTerritory(target.id)?.name ?? null;
    case "partner":
      return mockDb.partners.find((partner) => partner.id === target.id)?.name ?? null;
    case "product":
      return mockDb.products.find((product) => product.id === target.id)?.description ?? null;
    case "product_category":
      return MOCK_PRODUCT_CATEGORIES.find((category) => category.id === target.id)?.name ?? null;
  }
}

/** What a reader sees of a scheme: named targets, and never partner targets for a partner user. */
function forReader(scheme: SchemeWire): SchemeWire {
  const targets = scheme.targets
    .filter((target) => myPartner() === null || target.type !== "partner")
    .map((target) => ({ type: target.type, id: target.id, name: targetName(target) }));
  return { ...scheme, targets };
}

function refreshCurrent(scheme: SchemeWire): SchemeWire {
  const today = todayInIndia();
  return {
    ...scheme,
    is_current:
      scheme.is_active &&
      scheme.valid_from <= today &&
      (scheme.valid_to === null || scheme.valid_to >= today),
  };
}

const decimal = z.union([z.string(), z.number()]).transform(String);

const conditionSchema = z.object({
  metric: z.enum(CONDITION_METRICS).default("order_value"),
  min: decimal.default("0"),
  max: decimal.nullable().default(null),
});

const benefitSchema = z.object({
  kind: z.enum(BENEFIT_KINDS),
  value: decimal,
  cap: decimal.nullable().default(null),
  entitlement_days: z.number().int().nullable().default(null),
});

const targetSchema = z.object({ type: z.enum(TARGET_TYPES), id: z.string().min(1) });

const createSchema = z.object({
  code: z.string(),
  name: z.string(),
  description: z.string().nullable().default(null),
  scheme_type: z.enum(SCHEME_TYPES),
  condition: conditionSchema.default({ metric: "order_value", min: "0", max: null }),
  benefit: benefitSchema,
  period: z.enum(SCHEME_PERIODS).nullable().default(null),
  valid_from: z.string(),
  valid_to: z.string().nullable().default(null),
  priority: z.number().int().default(100),
  stackable: z.boolean().default(false),
  targets: z.array(targetSchema).default([]),
});

/** Only what was sent: no defaults, so a scheme's untouched fields stay untouched. */
const patchSchema = z.object({
  name: z.string().optional(),
  description: z.string().nullable().optional(),
  scheme_type: z.enum(SCHEME_TYPES).optional(),
  condition: z
    .object({ metric: z.enum(CONDITION_METRICS), min: decimal, max: decimal.nullable() })
    .optional(),
  benefit: z
    .object({
      kind: z.enum(BENEFIT_KINDS),
      value: decimal,
      cap: decimal.nullable(),
      entitlement_days: z.number().int().nullable(),
    })
    .optional(),
  period: z.enum(SCHEME_PERIODS).nullable().optional(),
  valid_from: z.string().optional(),
  valid_to: z.string().nullable().optional(),
  priority: z.number().int().optional(),
  stackable: z.boolean().optional(),
  targets: z.array(targetSchema).optional(),
  is_active: z.boolean().optional(),
});

type Terms = z.output<typeof createSchema>;

/** The backend's `domain.problems` and `target_problems`, by field. */
function problemsOf(terms: Terms): Record<string, string> {
  const out: Record<string, string> = {};
  if (!/^[A-Za-z0-9_-]{2,40}$/.test(terms.code)) out.code = "Letters, digits, - and _.";
  if (terms.name.trim() === "") out.name = "Required.";
  if (!KINDS_FOR_TYPE[terms.scheme_type].includes(terms.benefit.kind)) {
    out["benefit.kind"] = `This type takes ${KINDS_FOR_TYPE[terms.scheme_type].join(" or ")}.`;
  }
  const value = Number(terms.benefit.value);
  if (!(value > 0)) out["benefit.value"] = "Must be more than zero.";
  else if (terms.benefit.kind === "pct" && value > 100)
    out["benefit.value"] = "A percentage is at most 100.";
  else if (terms.benefit.kind === "points" && !Number.isInteger(value)) {
    out["benefit.value"] = "Points are whole numbers.";
  }
  if (terms.benefit.cap !== null && terms.benefit.kind === "points") {
    out["benefit.cap"] = "A points benefit has no cap.";
  }
  const needsDays =
    terms.scheme_type === "next_order" ||
    (terms.scheme_type === "period" && terms.benefit.kind !== "points");
  if (terms.benefit.entitlement_days !== null && !needsDays) {
    out["benefit.entitlement_days"] = "Only a benefit used on a later order expires.";
  }
  if (terms.scheme_type === "period") {
    if (terms.period === null) out.period = "A period scheme runs by month or quarter.";
    if (terms.valid_to === null) out.valid_to = "A period scheme needs an end date.";
  } else if (terms.period !== null) {
    out.period = "Only a period scheme has a period.";
  }
  if (terms.condition.max !== null && Number(terms.condition.max) < Number(terms.condition.min)) {
    out["condition.max"] = "Must be at least the minimum.";
  }
  if (terms.valid_to !== null && terms.valid_to < terms.valid_from) {
    out.valid_to = "Must be on or after the start date.";
  }
  const seen = new Set<string>();
  terms.targets.forEach((target, index) => {
    if (target.type === "partner_type" && !PARTNER_TYPES.some((type) => type === target.id)) {
      out[`targets[${String(index)}].id`] = "distributor, dealer or sub_dealer.";
    }
    const key = `${target.type}:${target.id}`;
    if (seen.has(key)) out[`targets[${String(index)}]`] = "Listed twice.";
    seen.add(key);
  });
  return out;
}

function toWire(
  id: string,
  terms: Terms,
  used: boolean,
  active: boolean,
  createdAt: string,
): SchemeWire {
  return refreshCurrent({
    id,
    code: terms.code,
    name: terms.name.trim(),
    description: terms.description,
    scheme_type: terms.scheme_type,
    condition: {
      metric: terms.condition.metric,
      min: Number(terms.condition.min).toFixed(3),
      max: terms.condition.max === null ? null : Number(terms.condition.max).toFixed(3),
    },
    benefit: {
      kind: terms.benefit.kind,
      value: Number(terms.benefit.value).toFixed(3),
      cap: terms.benefit.cap === null ? null : Number(terms.benefit.cap).toFixed(2),
      entitlement_days:
        terms.benefit.entitlement_days ??
        (terms.scheme_type === "next_order" ||
        (terms.scheme_type === "period" && terms.benefit.kind !== "points")
          ? 90
          : null),
    },
    period: terms.period,
    valid_from: terms.valid_from,
    valid_to: terms.valid_to,
    priority: terms.priority,
    stackable: terms.stackable,
    is_active: active,
    is_current: false,
    used,
    targets: terms.targets.map((target) => ({ type: target.type, id: target.id })),
    created_at: createdAt,
  });
}

function termsOf(scheme: SchemeWire): Terms {
  return {
    code: scheme.code,
    name: scheme.name,
    description: scheme.description,
    scheme_type: scheme.scheme_type,
    condition: scheme.condition,
    benefit: {
      kind: scheme.benefit.kind,
      value: scheme.benefit.value,
      cap: scheme.benefit.cap,
      entitlement_days: scheme.benefit.entitlement_days,
    },
    period: scheme.period,
    valid_from: scheme.valid_from,
    valid_to: scheme.valid_to,
    priority: scheme.priority,
    stackable: scheme.stackable,
    targets: scheme.targets.map((target) => ({ type: target.type, id: target.id })),
  };
}

/** The first day of the month after `day`'s: 2026-12-15 → 2027-01-01. */
function nextMonthStart(day: string): string {
  const [year = 0, month = 1] = day.split("-").map(Number);
  return month === 12
    ? `${String(year + 1)}-01-01`
    : `${String(year)}-${String(month + 1).padStart(2, "0")}-01`;
}

function needKey(request: Request): Response | null {
  return request.headers.get("idempotency-key") === null
    ? errorResponse(400, "idempotency_key_required", "Send an Idempotency-Key.")
    : null;
}

function inUse(): Response {
  return errorResponse(
    409,
    "scheme_in_use",
    "This scheme has given benefits. Only its end date and active flag can change; end it and create a new one.",
  );
}

export const schemeHandlers = [
  http.get(buildApiUrl("/schemes"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!may("view")) return errorResponse(403, "insufficient_permission", "No schemes.view.");
    const params = new URL(request.url).searchParams;
    const status = params.get("status");
    const type = params.get("scheme_type");
    const q = (params.get("q") ?? "").trim().toLowerCase();
    const partner = myPartner();
    const rows = mockDb.schemes
      .map(refreshCurrent)
      .filter((scheme) => (partner === null ? true : scheme.is_active && aimedAt(scheme, partner)))
      .filter((scheme) =>
        status === "current"
          ? scheme.is_current
          : status === "active"
            ? scheme.is_active
            : status === "inactive"
              ? !scheme.is_active
              : true,
      )
      .filter((scheme) => type === null || scheme.scheme_type === type)
      .filter(
        (scheme) =>
          q === "" ||
          scheme.code.toLowerCase().includes(q) ||
          scheme.name.toLowerCase().includes(q),
      )
      .sort((left, right) => right.created_at.localeCompare(left.created_at));
    const cursor = params.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const page = rows.slice(offset, offset + PAGE);
    return HttpResponse.json({
      data: page.map(forReader),
      meta:
        offset + PAGE < rows.length
          ? { limit: PAGE, next_cursor: encodeCursor(offset + PAGE) }
          : { limit: PAGE },
    });
  }),

  http.post(buildApiUrl("/schemes"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const missing = needKey(request);
    if (missing) return missing;
    if (!may("create")) return errorResponse(403, "insufficient_permission", "No schemes.create.");
    const parsed = createSchema.safeParse(await request.json());
    if (!parsed.success)
      return errorResponse(422, "validation_error", "Bad request.", {
        scheme_type: "Check the scheme.",
      });
    const problems = problemsOf(parsed.data);
    if (Object.keys(problems).length > 0) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", problems);
    }
    if (
      mockDb.schemes.some((scheme) => scheme.code.toLowerCase() === parsed.data.code.toLowerCase())
    ) {
      return errorResponse(409, "code_taken", "A scheme with this code exists.", {
        code: "Taken.",
      });
    }
    const created = toWire(
      mockSchemeId(mockDb.schemes.length + 100),
      parsed.data,
      false,
      true,
      new Date().toISOString(),
    );
    mockDb.schemes.unshift(created);
    return HttpResponse.json({ data: created }, { status: 201 });
  }),

  http.get(buildApiUrl("/schemes/:schemeId/standing"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const scheme = mockDb.schemes.find((item) => item.id === String(params.schemeId));
    if (scheme === undefined) return errorResponse(404, "not_found", "No such scheme.");
    if (scheme.scheme_type !== "period") {
      return errorResponse(422, "not_a_period_scheme", "Only a period scheme has a standing.");
    }
    const partnerId = myPartner()?.id ?? new URL(request.url).searchParams.get("partner_id");
    if (partnerId === null) {
      return errorResponse(422, "validation_error", "Name the partner.", {
        partner_id: "Required.",
      });
    }
    const today = todayInIndia();
    if (scheme.valid_from > today)
      return errorResponse(404, "not_found", "The scheme has not started.");
    const start = `${today.slice(0, 7)}-01`;
    const min = Number(scheme.condition.min);
    let seed = 0;
    for (const char of partnerId) seed = (seed * 31 + char.charCodeAt(0)) % 997;
    const achieved = Math.round((min * (35 + (seed % 90))) / 100);
    const standing: StandingWire = {
      period_start: start,
      period_end: shiftCalendarDay(nextMonthStart(today), -1),
      metric: scheme.condition.metric,
      achieved: String(achieved),
      min: scheme.condition.min,
      max: scheme.condition.max,
      qualifies: achieved >= min,
    };
    return HttpResponse.json({ data: standing });
  }),

  http.get(buildApiUrl("/schemes/:schemeId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!may("view")) return errorResponse(403, "insufficient_permission", "No schemes.view.");
    const scheme = mockDb.schemes.find((item) => item.id === String(params.schemeId));
    const partner = myPartner();
    if (scheme === undefined || (partner !== null && !aimedAt(scheme, partner))) {
      return errorResponse(404, "not_found", "No such scheme.");
    }
    return HttpResponse.json({ data: forReader(refreshCurrent(scheme)) });
  }),

  http.patch(buildApiUrl("/schemes/:schemeId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const missing = needKey(request);
    if (missing) return missing;
    if (!may("edit")) return errorResponse(403, "insufficient_permission", "No schemes.edit.");
    const index = mockDb.schemes.findIndex((item) => item.id === String(params.schemeId));
    const current = mockDb.schemes[index];
    if (current === undefined) return errorResponse(404, "not_found", "No such scheme.");
    const parsed = patchSchema.safeParse(await request.json());
    if (!parsed.success) return errorResponse(422, "validation_error", "Bad request.", {});
    const { is_active: active, ...changes } = parsed.data;
    if (current.used) {
      const others = Object.keys(changes).filter((key) => key !== "valid_to");
      if (others.length > 0) return inUse();
      if (changes.valid_to !== undefined) {
        const today = todayInIndia();
        if (
          changes.valid_to === null ||
          changes.valid_to < today ||
          (current.valid_to !== null && changes.valid_to > current.valid_to)
        ) {
          return inUse();
        }
      }
    }
    const base = termsOf(current);
    const terms: Terms = {
      code: base.code,
      name: changes.name ?? base.name,
      description: changes.description === undefined ? base.description : changes.description,
      scheme_type: changes.scheme_type ?? base.scheme_type,
      condition: changes.condition ?? base.condition,
      benefit: changes.benefit ?? base.benefit,
      period: changes.period === undefined ? base.period : changes.period,
      valid_from: changes.valid_from ?? base.valid_from,
      valid_to: changes.valid_to === undefined ? base.valid_to : changes.valid_to,
      priority: changes.priority ?? base.priority,
      stackable: changes.stackable ?? base.stackable,
      targets: changes.targets ?? base.targets,
    };
    const problems = problemsOf(terms);
    if (Object.keys(problems).length > 0) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", problems);
    }
    const saved = toWire(
      current.id,
      terms,
      current.used,
      active ?? current.is_active,
      current.created_at,
    );
    mockDb.schemes[index] = saved;
    return HttpResponse.json({ data: saved });
  }),

  http.get(buildApiUrl("/scheme-entitlements"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!may("view")) return errorResponse(403, "insufficient_permission", "No schemes.view.");
    const params = new URL(request.url).searchParams;
    const status = params.get("status");
    const partner = myPartner();
    const partnerId = partner?.id ?? params.get("partner_id");
    const rows = mockDb.entitlements.filter(
      (credit) =>
        (status === null || credit.status === status) &&
        (partnerId === null || credit.partner.id === partnerId),
    );
    return HttpResponse.json({ data: rows, meta: { limit: PAGE } });
  }),

  /** Names a scheme's territory target (GET /territories/{id}); staff only, as the backend. */
  http.get(buildApiUrl("/territories/:territoryId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (isPartnerRole(role())) return errorResponse(403, "insufficient_permission", "Staff only.");
    const territory = MOCK_TERRITORIES.find((item) => item.id === String(params.territoryId));
    if (territory === undefined) return errorResponse(404, "not_found", "No such territory.");
    return HttpResponse.json({
      data: { id: territory.id, name: territory.name, level: territory.level },
    });
  }),
];
