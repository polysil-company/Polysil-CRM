import { http, HttpResponse } from "msw";
import { z } from "zod";

import { TERRITORY_LEVELS } from "@/features/masters/api/masters.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { MOCK_ID_SPACE, mockUuid } from "@/mocks/data/reference";
import { MOCK_TERRITORIES, type MockAdminTerritory } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { decodeCursor, encodeCursor, errorResponse } from "./shared";

/**
 * MSTR-012 · The territory tree for Masters (`backend/docs/api/territories.md`):
 *  - anyone signed in reads it; those who may edit masters add and change;
 *  - a state sits at the root, each other level under the level above;
 *  - names are unique among siblings and codes unique per level (case-insensitively);
 *  - a state's code locks once a lead is numbered under it (POL/<code>/…).
 * The admin copy is the mock's own: the pickers (`/lookups/territories`) keep the seed.
 */

const SEEDED_AT = "2026-04-01T04:30:00.000Z";

function territories(): MockAdminTerritory[] {
  if (mockDb.territories !== null) return mockDb.territories;
  mockDb.territories = MOCK_TERRITORIES.map((territory) => ({
    id: territory.id,
    name: territory.name,
    level: TERRITORY_LEVELS.find((level) => level === territory.level) ?? "village",
    code: territory.code ?? null,
    parent: territory.parent ?? null,
    created_at: SEEDED_AT,
  }));
  return mockDb.territories;
}

function codeLocked(territory: MockAdminTerritory): boolean {
  if (territory.level !== "state" || territory.code === null) return false;
  const prefix = `POL/${territory.code}/`;
  return mockDb.leads.some((lead) => lead.inquiry_no.startsWith(prefix));
}

function toWire(territory: MockAdminTerritory): unknown {
  return { ...territory, code_locked: codeLocked(territory) };
}

function mayEdit(): boolean {
  return can(mockPermissionsFor(readMockRole()), "masters", "edit");
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function same(left: string, right: string): boolean {
  return left.trim().toLowerCase() === right.trim().toLowerCase();
}

/** Whose sibling a name would be, and whose level a code would share. */
function clash(
  input: { name?: string; code?: string | null; level: string; parentId: string | null },
  except: string | null,
): Record<string, string> | null {
  const others = territories().filter((territory) => territory.id !== except);
  if (
    input.name !== undefined &&
    others.some(
      (territory) =>
        (territory.parent?.id ?? null) === input.parentId && same(territory.name, input.name ?? ""),
    )
  ) {
    return { name: "a territory with this name is already there" };
  }
  const code = input.code;
  if (
    code !== undefined &&
    code !== null &&
    others.some(
      (territory) =>
        territory.level === input.level && territory.code !== null && same(territory.code, code),
    )
  ) {
    return { code: "another territory at this level has this code" };
  }
  return null;
}

const createSchema = z.object({
  name: z.string().trim().min(1).max(120),
  level: z.enum(TERRITORY_LEVELS),
  parent_id: z.string().nullish(),
  code: z.string().trim().max(10).nullish(),
});

const patchSchema = z.object({
  name: z.string().trim().min(1).max(120).optional(),
  code: z.string().trim().max(10).nullable().optional(),
});

function codeOf(value: string | null | undefined): string | null {
  return value == null || value.trim() === "" ? null : value.trim().toUpperCase();
}

export const territoryHandlers = [
  http.get(buildApiUrl("/territories"), async ({ request }) => {
    const { scenario, failure } = await applyScenario();
    if (failure) return failure;
    const url = new URL(request.url);
    const level = url.searchParams.get("level");
    const parentId = url.searchParams.get("parent_id");
    const q = (url.searchParams.get("q") ?? "").trim().toLowerCase();
    const rows =
      scenario === "empty"
        ? []
        : territories().filter(
            (territory) =>
              (level === null || territory.level === level) &&
              (parentId === null || territory.parent?.id === parentId) &&
              (q === "" ||
                territory.name.toLowerCase().includes(q) ||
                (territory.code ?? "").toLowerCase().includes(q)),
          );
    const cursor = url.searchParams.get("cursor");
    const offset = cursor === null ? 0 : (decodeCursor(cursor) ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? "50");
    const page = rows.slice(offset, offset + limit);
    return HttpResponse.json({
      data: page.map(toWire),
      meta: {
        limit,
        next_cursor: offset + limit < rows.length ? encodeCursor(offset + limit) : null,
      },
    });
  }),

  http.get(buildApiUrl("/territories/:territoryId"), async ({ params }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const territory = territories().find((item) => item.id === String(params.territoryId));
    if (territory === undefined) return errorResponse(404, "not_found", "No such territory.");
    return HttpResponse.json({ data: toWire(territory) });
  }),

  http.post(buildApiUrl("/territories"), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit())
      return errorResponse(403, "insufficient_permission", "You may not edit masters.");
    const parsed = createSchema.safeParse(await request.json());
    if (!parsed.success) {
      const fields: Record<string, string> = {};
      for (const issue of parsed.error.issues) fields[String(issue.path[0])] = issue.message;
      return invalid(fields);
    }
    const body = parsed.data;
    const depth = TERRITORY_LEVELS.indexOf(body.level);
    const parentId = body.parent_id ?? null;
    let parent: MockAdminTerritory | undefined;
    if (depth === 0) {
      if (parentId !== null) return invalid({ parent_id: "a state has no parent" });
    } else {
      const expected = TERRITORY_LEVELS[depth - 1] ?? "state";
      parent = territories().find((item) => item.id === parentId);
      if (parentId === null || parent === undefined) {
        return invalid({ parent_id: `a ${body.level} sits under a ${expected}` });
      }
      if (parent.level !== expected) {
        return invalid({ parent_id: `a ${body.level} sits under a ${expected}` });
      }
    }
    const code = codeOf(body.code);
    const problem = clash({ name: body.name, code, level: body.level, parentId }, null);
    if (problem !== null) return invalid(problem);
    const created: MockAdminTerritory = {
      id: mockUuid(MOCK_ID_SPACE.territory, 5000 + territories().length),
      name: body.name,
      level: body.level,
      code,
      parent:
        parent === undefined ? null : { id: parent.id, name: parent.name, level: parent.level },
      created_at: new Date().toISOString(),
    };
    territories().unshift(created);
    return HttpResponse.json({ data: toWire(created) }, { status: 201 });
  }),

  http.patch(buildApiUrl("/territories/:territoryId"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit())
      return errorResponse(403, "insufficient_permission", "You may not edit masters.");
    const territory = territories().find((item) => item.id === String(params.territoryId));
    if (territory === undefined) return errorResponse(404, "not_found", "No such territory.");
    const parsed = patchSchema.safeParse(await request.json());
    if (!parsed.success) return invalid({ name: "1 to 120 characters" });
    const body = parsed.data;
    if (body.name === undefined && body.code === undefined)
      return invalid({ body: "nothing to change" });
    const code = body.code === undefined ? undefined : codeOf(body.code);
    if (code !== undefined && code !== territory.code && codeLocked(territory)) {
      return invalid({ code: "leads are numbered with this state's code: it can't change" });
    }
    const problem = clash(
      {
        ...(body.name === undefined ? {} : { name: body.name }),
        ...(code === undefined ? {} : { code }),
        level: territory.level,
        parentId: territory.parent?.id ?? null,
      },
      territory.id,
    );
    if (problem !== null) return invalid(problem);
    if (body.name !== undefined) territory.name = body.name;
    if (code !== undefined) territory.code = code;
    return HttpResponse.json({ data: toWire(territory) });
  }),
];
