import { http, HttpResponse } from "msw";
import { z } from "zod";

import type {
  SchemeDetailWire,
  SchemeRowWire,
} from "@/features/subsidy/api/subsidy-schemes.schemas";
import { systemTypeSchema } from "@/features/subsidy/api/subsidy.schemas";
import { buildApiUrl } from "@/lib/api/url";
import { can } from "@/lib/auth/permissions";
import { readMockRole } from "@/lib/dev/mock-settings";
import { todayInIndia } from "@/lib/format";
import { mockPermissionsFor } from "@/mocks/data/permissions";
import { emptySubsidyMasters } from "@/mocks/data/subsidy-masters";
import type { MockScheme } from "@/mocks/data/subsidy-schemes";
import { findMockTerritory } from "@/mocks/data/territories";
import { mockDb } from "@/mocks/db";

import { applyScenario } from "./scenario";
import { errorResponse } from "./shared";
import { mockApplications } from "./subsidy-applications";
import { missingFor, mockScheme, schemeReady, systemsOf } from "./subsidy-readiness";

/**
 * SUBS-014 · Subsidy schemes, one per state, with migration 044's rules: a new scheme copies its
 * template's systems and stages but no figure; one active scheme per state; a scheme's state is
 * set once; and an active scheme with no state (legacy mode) never sits beside one with a state.
 */

const createSchema = z.object({
  code: z
    .string()
    .trim()
    .regex(/^[A-Za-z0-9_]{2,20}$/, "2 to 20 of A-Z, 0-9 and _"),
  name: z.string().trim().min(1).max(200),
  state_territory_id: z.string().min(1),
  template: z.string().default("GGRC"),
  systems: z.array(systemTypeSchema).nullable().default(null),
});

const patchSchema = z
  .object({
    name: z.string().trim().min(1).max(200).optional(),
    is_active: z.boolean().optional(),
    state_territory_id: z.string().min(1).optional(),
  })
  .refine((body) => Object.keys(body).length > 0, "Send at least one field.");

const renameSchema = z.object({ name: z.string().trim().min(1).max(120) });

function mayEdit(): boolean {
  return can(mockPermissionsFor(readMockRole()), "masters", "edit");
}

function fieldsOf(error: z.ZodError): Record<string, string> {
  const fields: Record<string, string> = {};
  for (const issue of error.issues)
    fields[issue.path.map(String).join(".") || "body"] = issue.message;
  return fields;
}

function invalid(fields: Record<string, string>): Response {
  return errorResponse(422, "validation_error", "Some fields need correcting.", fields);
}

function isState(id: string): boolean {
  return findMockTerritory(id)?.level === "state";
}

function stateOf(scheme: MockScheme): SchemeRowWire["state"] {
  if (scheme.state_territory_id === null) return null;
  const territory = findMockTerritory(scheme.state_territory_id);
  if (territory === undefined) return null;
  return { id: territory.id, code: territory.code ?? "", name: territory.name };
}

/** The two modes never mix: an active scheme with no state beside one with a state. */
function mixesModes(schemes: readonly MockScheme[]): boolean {
  const active = schemes.filter((scheme) => scheme.is_active);
  return (
    active.some((scheme) => scheme.state_territory_id === null) &&
    active.some((scheme) => scheme.state_territory_id !== null)
  );
}

function stateTaken(state: string, except: string): boolean {
  return mockDb.subsidySchemes.some(
    (scheme) => scheme.is_active && scheme.code !== except && scheme.state_territory_id === state,
  );
}

const STATE_TAKEN = (): Response =>
  errorResponse(409, "state_has_scheme", "Another active scheme already covers this state.", {
    state_territory_id: "already has an active scheme",
  });

const UNLINKED = (): Response =>
  errorResponse(
    409,
    "unlinked_scheme_exists",
    "An active scheme has no state. Link it to its state first.",
  );

function toRow(scheme: MockScheme): SchemeRowWire {
  return {
    code: scheme.code,
    name: scheme.name,
    is_active: scheme.is_active,
    state: stateOf(scheme),
    systems: systemsOf(scheme),
    ready: schemeReady(scheme, todayInIndia()),
    applications: mockApplications().filter((item) => item.scheme === scheme.code).length,
  };
}

function toDetail(scheme: MockScheme, on: string): SchemeDetailWire {
  return {
    code: scheme.code,
    name: scheme.name,
    is_active: scheme.is_active,
    state: stateOf(scheme),
    on,
    systems: systemsOf(scheme).map((system) => {
      const missing = missingFor(scheme.code, system, on);
      return { system_type: system, ready: missing.length === 0, missing };
    }),
    stages: scheme.stages.map((stage) => ({ ...stage })),
    ready: schemeReady(scheme, on),
  };
}

const base = (rest = ""): string => buildApiUrl(`/subsidy-schemes${rest}`);

export const subsidySchemeHandlers = [
  http.get(base(), async () => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const rows = [...mockDb.subsidySchemes]
      .sort((a, b) => Number(b.is_active) - Number(a.is_active) || a.code.localeCompare(b.code))
      .map(toRow);
    return HttpResponse.json({ data: rows });
  }),

  http.post(base(), async ({ request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit()) return errorResponse(403, "forbidden", "Not permitted.");
    const parsed = createSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    if (!isState(body.state_territory_id)) return invalid({ state_territory_id: "Not a state." });
    const template = mockScheme(body.template);
    if (
      template === undefined ||
      !template.is_active ||
      !template.stages.some((s) => s.is_active)
    ) {
      return invalid({ template: "Not an active scheme with stages." });
    }
    const systems = body.systems ?? template.systems;
    if (systems.length === 0 || systems.some((system) => !template.systems.includes(system))) {
      return invalid({ systems: "The template does not have every one of these." });
    }
    const code = body.code.toUpperCase();
    if (mockDb.subsidySchemes.some((scheme) => scheme.code === code)) {
      return errorResponse(409, "code_taken", "A scheme with this code exists.", {
        code: "already used",
      });
    }
    if (stateTaken(body.state_territory_id, code)) return STATE_TAKEN();
    const scheme: MockScheme = {
      code,
      name: body.name,
      is_active: true,
      state_territory_id: body.state_territory_id,
      systems: systemsOf({ ...template, systems }),
      stages: template.stages.map((stage) => ({ ...stage })),
    };
    if (mixesModes([...mockDb.subsidySchemes, scheme])) return UNLINKED();
    mockDb.subsidySchemes.push(scheme);
    mockDb.subsidyMasters.set(code, emptySubsidyMasters());
    return HttpResponse.json({ data: toDetail(scheme, todayInIndia()) }, { status: 201 });
  }),

  http.get(base("/:code"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    const scheme = mockScheme(String(params.code));
    if (scheme === undefined) return errorResponse(404, "not_found", "No such scheme.");
    const on = new URL(request.url).searchParams.get("on") ?? todayInIndia();
    return HttpResponse.json({ data: toDetail(scheme, on) });
  }),

  http.patch(base("/:code"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit()) return errorResponse(403, "forbidden", "Not permitted.");
    const scheme = mockScheme(String(params.code));
    if (scheme === undefined) return errorResponse(404, "not_found", "No such scheme.");
    const parsed = patchSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    const body = parsed.data;
    if (body.state_territory_id !== undefined) {
      if (scheme.state_territory_id !== null) {
        return errorResponse(
          409,
          "state_fixed",
          "The scheme already has a state; it does not change.",
          {
            state_territory_id: "already set",
          },
        );
      }
      if (!isState(body.state_territory_id)) return invalid({ state_territory_id: "Not a state." });
    }
    const next: MockScheme = {
      ...scheme,
      name: body.name ?? scheme.name,
      is_active: body.is_active ?? scheme.is_active,
      state_territory_id: body.state_territory_id ?? scheme.state_territory_id,
    };
    if (
      next.is_active &&
      next.state_territory_id !== null &&
      stateTaken(next.state_territory_id, next.code)
    ) {
      return STATE_TAKEN();
    }
    if (mixesModes(mockDb.subsidySchemes.map((item) => (item.code === next.code ? next : item)))) {
      return UNLINKED();
    }
    scheme.name = next.name;
    scheme.is_active = next.is_active;
    scheme.state_territory_id = next.state_territory_id;
    return HttpResponse.json({ data: toDetail(scheme, todayInIndia()) });
  }),

  http.patch(base("/:code/stages/:stageCode"), async ({ params, request }) => {
    const { failure } = await applyScenario();
    if (failure) return failure;
    if (!mayEdit()) return errorResponse(403, "forbidden", "Not permitted.");
    const scheme = mockScheme(String(params.code));
    const stage = scheme?.stages.find((item) => item.code === params.stageCode);
    if (stage === undefined) return errorResponse(404, "not_found", "No such scheme or stage.");
    const parsed = renameSchema.safeParse(await request.json());
    if (!parsed.success) return invalid(fieldsOf(parsed.error));
    stage.name = parsed.data.name;
    return HttpResponse.json({ data: { ...stage } });
  }),
];
