import { http, HttpResponse } from "msw";
import { z } from "zod";

import type { PartnerPickListWire } from "@/features/leads/api/leads.schemas";
import {
  LOOKUP_LISTS,
  type LookupList,
  type LookupListWire,
  type TerritoryListWire,
} from "@/features/lookups/api/lookups.schemas";
import type { LookupItemResponse, ScoringResponse } from "@/features/masters/api/masters.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

const DEFAULT_TERRITORY_LIMIT = 50;
const MAX_TERRITORY_LIMIT = 100;
const TERRITORY_LEVELS: readonly string[] = ["state", "district", "taluka", "village"];
const DEFAULT_PARTNER_LIMIT = 50;

/** Where each list's added rows take their mock ids from. */
const LIST_SLOT: Readonly<Record<LookupList, number>> = {
  "lead-sources": 1,
  "mis-systems": 2,
  "lost-reasons": 3,
  crops: 4,
  "meeting-types": 5,
  "complaint-types": 6,
};

/** Caps and hour bands must stay above zero (the backend's rule 7). */
const POSITIVE_SCORING_KEYS: ReadonlySet<string> = new Set([
  "value_cap",
  "engagement_cap",
  "speed_fast_hours",
  "speed_slow_hours",
  "dormant_after_days",
]);

const lookupCreateSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^[a-z0-9_]{1,50}$/),
  name: z.string().trim().min(1).max(100),
  sort_order: z.number().int().nullish(),
  quality: z.union([z.string(), z.number()]).nullish(),
  kind: z.enum(["won", "lost"]).nullish(),
});

const lookupUpdateSchema = z.object({
  is_active: z.boolean().nullish(),
  sort_order: z.number().int().nullish(),
  quality: z.union([z.string(), z.number()]).nullish(),
});

const scoringPatchSchema = z.object({
  values: z.record(z.string(), z.union([z.string(), z.number()])),
});

/** Quality is stored at two places: 0.555 comes back "0.56". */
function qualityText(value: string | number): string {
  return (Math.round(Number(value) * 100) / 100).toFixed(2);
}

function mayEditMasters(): boolean {
  return can(mockPermissionsFor(readMockRole()), "masters", "edit");
}

function forbidden(): Response {
  return errorResponse(403, "insufficient_permission", "The action is not in your permissions.");
}

/**
 * MSTR-002 · GET /lookups/* as the backend serves them (backend/docs/api/lookups.md). The
 * lists are small and never empty, so the "empty" scenario leaves them alone: a New lead form
 * with no systems to choose from would preview nothing useful.
 */
export const lookupHandlers = [
  ...LOOKUP_LISTS.map((list) =>
    http.get(buildApiUrl(`/lookups/${list}`), async () => {
      const { failure } = await applyScenario();
      if (failure) return failure;

      // BE-026 · quality only for those who may edit masters
      const rows = mockDb.lookups[list].map((row) =>
        mayEditMasters() ? row : { ...row, quality: row.quality === undefined ? undefined : null },
      );
      const body: LookupListWire = { data: rows };
      return HttpResponse.json(body);
    }),
  ),

  // MSTR-009 · Add a row; switch one on or off. Rows are never renamed or deleted.
  ...LOOKUP_LISTS.map((list) =>
    http.post(buildApiUrl(`/lookups/${list}`), async ({ request }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;
      if (!mayEditMasters()) return forbidden();

      const parsed = lookupCreateSchema.safeParse(await request.json());
      if (!parsed.success) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          code: "lowercase letters, digits and underscores, 1 to 50",
        });
      }
      const rows = mockDb.lookups[list];
      if (rows.some((row) => row.code === parsed.data.code)) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          code: "already in use",
        });
      }
      const ordered = list === "lead-sources" || list === "lost-reasons";
      const row = {
        id: mockUuid(MOCK_ID_SPACE.lookup, 9000 + LIST_SLOT[list] * 100 + rows.length + 1),
        code: parsed.data.code,
        name: parsed.data.name,
        is_active: true,
        sort_order: ordered ? (parsed.data.sort_order ?? 0) : null,
        quality: list === "lead-sources" ? qualityText(parsed.data.quality ?? "0.5") : null,
        kind: list === "lost-reasons" ? (parsed.data.kind ?? "lost") : null,
      };
      mockDb.lookups[list] = [...rows, row];
      const body: LookupItemResponse = { data: row };
      return HttpResponse.json(body, { status: 201 });
    }),
  ),
  ...LOOKUP_LISTS.map((list) =>
    http.patch(buildApiUrl(`/lookups/${list}/:itemId`), async ({ params, request }) => {
      const { failure } = await applyScenario();
      if (failure) return failure;
      if (!mayEditMasters()) return forbidden();

      const row = mockDb.lookups[list].find((item) => item.id === String(params.itemId));
      if (row === undefined) return errorResponse(404, "not_found", "No such row.");
      const parsed = lookupUpdateSchema.safeParse(await request.json());
      if (!parsed.success) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          quality: "0 to 1",
        });
      }
      const { sort_order: sortOrder, quality } = parsed.data;
      if (sortOrder != null && Math.abs(sortOrder) > 1_000_000) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          sort_order: "at most 1,000,000 either way",
        });
      }
      if (quality != null && !(Number(quality) >= 0 && Number(quality) <= 1)) {
        return errorResponse(422, "validation_error", "Some fields need correcting.", {
          quality: "0 to 1",
        });
      }
      const updated = {
        ...row,
        is_active: parsed.data.is_active ?? row.is_active ?? true,
        ...(sortOrder == null ? {} : { sort_order: sortOrder }),
        ...(quality == null ? {} : { quality: qualityText(quality) }),
      };
      mockDb.lookups[list] = mockDb.lookups[list].map((item) =>
        item.id === row.id ? updated : item,
      );
      const body: LookupItemResponse = { data: updated };
      return HttpResponse.json(body);
    }),
  ),

  // MSTR-010 · The lead score's settings: readable by anyone signed in, changed with masters.edit.
  http.get(buildApiUrl("/lookups/scoring"), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const body: ScoringResponse = { data: mockDb.scoring };
    return HttpResponse.json(body);
  }),
  http.patch(buildApiUrl("/lookups/scoring"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEditMasters()) return forbidden();

    const parsed = scoringPatchSchema.safeParse(await request.json());
    if (!parsed.success) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        values: "numbers, by key",
      });
    }
    const fields: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed.data.values)) {
      const number = Number(value);
      if (!mockDb.scoring.some((item) => item.key === key)) fields[key] = "unknown setting";
      else if (!Number.isFinite(number) || number < 0) fields[key] = "must not be negative";
      else if (POSITIVE_SCORING_KEYS.has(key) && Number(number.toFixed(2)) <= 0) {
        fields[key] = "must be more than 0";
      }
    }
    if (Object.keys(fields).length > 0) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
    }
    mockDb.scoring = mockDb.scoring.map((item) => {
      const value = parsed.data.values[item.key];
      return value === undefined ? item : { ...item, value: Number(value).toFixed(2) };
    });
    const body: ScoringResponse = { data: mockDb.scoring };
    return HttpResponse.json(body);
  }),

  /**
   * LEAD-008 · GET /lookups/partners — every mock partner, those added in the admin too (the
   * mock does not scope them), by name, code or contact person containing `q` (backend #49),
   * ordered by name.
   */
  http.get(buildApiUrl("/lookups/partners"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const limit = Math.min(
      MAX_TERRITORY_LIMIT,
      Number(url.searchParams.get("limit") ?? DEFAULT_PARTNER_LIMIT) || DEFAULT_PARTNER_LIMIT,
    );
    const body: PartnerPickListWire = {
      data:
        scenario === "empty"
          ? []
          : mockDb.partners
              .filter(
                (partner) =>
                  q === "" ||
                  partner.name.toLowerCase().includes(q) ||
                  (partner.contact_name ?? "").toLowerCase().includes(q) ||
                  partner.code.toLowerCase().includes(q),
              )
              .map((partner) => ({
                id: partner.id,
                code: partner.code,
                name: partner.name,
                partner_type: partner.partner_type,
                territory: partner.territory,
              }))
              .sort((a, b) => a.name.localeCompare(b.name, "en-IN"))
              .slice(0, limit),
    };
    return HttpResponse.json(body);
  }),

  /**
   * Name contains `q` (any case), optionally one `level` or several `levels` (never both) and
   * one `parent_id`, ordered by name.
   */
  http.get(buildApiUrl("/lookups/territories"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const level = url.searchParams.get("level");
    const levels =
      url.searchParams
        .get("levels")
        ?.split(",")
        .map((part) => part.trim()) ?? null;
    if (
      levels !== null &&
      (level !== null || levels.some((part) => !TERRITORY_LEVELS.includes(part)))
    ) {
      return errorResponse(422, "validation_error", "Some fields need correcting.", {
        levels:
          level === null ? "unknown territory level" : "send either level or levels, not both",
      });
    }
    const parentId = url.searchParams.get("parent_id");
    const limit = Math.min(
      MAX_TERRITORY_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_TERRITORY_LIMIT) || 1),
    );

    const matches = MOCK_TERRITORIES.filter(
      (territory) =>
        (level === null || territory.level === level) &&
        (levels === null || levels.includes(territory.level)) &&
        (parentId === null || territory.parent?.id === parentId) &&
        (q === "" || territory.name.toLowerCase().includes(q)),
    )
      .sort((a, b) => a.name.localeCompare(b.name, "en-IN"))
      .slice(0, limit);

    const body: TerritoryListWire = {
      data: matches.map((territory) => ({
        id: territory.id,
        name: territory.name,
        level: territory.level,
        code: territory.code ?? null,
        parent: territory.parent ?? null,
      })),
    };
    return HttpResponse.json(body);
  }),
];
