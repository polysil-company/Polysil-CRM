import { http, HttpResponse } from "msw";

import type { PartnerPickListWire } from "@/features/leads/api/leads.schemas";
import {
  LOOKUP_LISTS,
  type LookupListWire,
  type TerritoryListWire,
} from "@/features/lookups/api/lookups.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { mockLookupRows } from "@/mocks/data/lookups";
import { MOCK_PARTNERS } from "@/mocks/data/reference";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";

const DEFAULT_TERRITORY_LIMIT = 50;
const MAX_TERRITORY_LIMIT = 100;
const TERRITORY_LEVELS: readonly string[] = ["state", "district", "taluka", "village"];
const DEFAULT_PARTNER_LIMIT = 50;

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

      const body: LookupListWire = { data: mockLookupRows(list) };
      return HttpResponse.json(body);
    }),
  ),

  /**
   * LEAD-008 · GET /lookups/partners — every mock partner (the mock does not scope them), by
   * name or code containing `q`, ordered by name.
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
          : MOCK_PARTNERS.map((partner, index) => ({
              id: partner.id,
              code: `CP-${String(index + 1).padStart(3, "0")}`,
              name: partner.name,
              partner_type: partner.partner_type,
              territory:
                MOCK_TERRITORIES.filter(
                  (territory) =>
                    territory.level === "district" && territory.name === partner.district,
                ).map(({ id, name, level }) => ({ id, name, level }))[0] ?? null,
            }))
              .filter(
                (partner) =>
                  q === "" ||
                  partner.name.toLowerCase().includes(q) ||
                  partner.code.toLowerCase().includes(q),
              )
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
