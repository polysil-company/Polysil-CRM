import { http, HttpResponse } from "msw";

import {
  LOOKUP_LISTS,
  type LookupListWire,
  type TerritoryListWire,
} from "@/features/lookups/api/lookups.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { mockLookupRows } from "@/mocks/data/lookups";
import { MOCK_TERRITORIES } from "@/mocks/data/territories";

import { applyScenario } from "./scenario";

const DEFAULT_TERRITORY_LIMIT = 50;
const MAX_TERRITORY_LIMIT = 100;

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

  /** Name contains `q` (any case), optionally one `level` and one `parent_id`, ordered by name. */
  http.get(buildApiUrl("/lookups/territories"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;

    const url = new URL(request.url);
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const level = url.searchParams.get("level");
    const parentId = url.searchParams.get("parent_id");
    const limit = Math.min(
      MAX_TERRITORY_LIMIT,
      Math.max(1, Number(url.searchParams.get("limit") ?? DEFAULT_TERRITORY_LIMIT) || 1),
    );

    const matches = MOCK_TERRITORIES.filter(
      (territory) =>
        (level === null || territory.level === level) &&
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
